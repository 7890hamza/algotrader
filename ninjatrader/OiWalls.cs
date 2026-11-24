// OiWalls - option walls (STS "find key levels with QQQ" method) on a NinjaTrader 8 chart.
//
// Draws 5 step lines that move during the day, like the OFB GEX study:
//   Outer call wall, Call wall (green), Flip (yellow), Put wall, Outer put wall (red)
// The levels come from scripts\windows\oi-walls.bat (AlgoTrader), which reads QQQ / SPY option
// open interest (today's 0DTE + this Friday) from Yahoo every 5 minutes, converts them to NQ / ES
// with the morning's NQ/QQQ (or ES/SPY) ratio and appends them to
//   Documents\AlgoTraderLevels\NQ.csv  and  ES.csv
// This indicator reads that file (and re-reads it when it changes). It never places orders.
//
// Install: copy this file to  Documents\NinjaTrader 8\bin\Custom\Indicators\
//          then New > NinjaScript Editor, press F5 to compile.
// Use:     add "OiWalls" to an NQ / MNQ or ES / MES chart (any timeframe). Keep oi-walls.bat running.
//
// Each level is a zone, not a tick-exact price: STS expects reactions within about 10-20 NQ points.
#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Gui;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class OiWalls : Indicator
    {
        private struct Snap
        {
            public DateTime Time;      // in NinjaTrader's time zone
            public double[] Levels;    // outer call, call, flip, put, outer put (NaN = none)
        }

        private readonly List<Snap> snaps = new List<Snap>();
        private string filePath;
        private DateTime fileStamp = DateTime.MinValue;
        private DateTime lastCheck = DateTime.MinValue;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Option walls (call wall, put wall, flip) from QQQ / SPY open interest, written by AlgoTrader's oi-walls.bat.";
                Name = "OiWalls";
                Calculate = Calculate.OnPriceChange;
                IsOverlay = true;
                DisplayInDataBox = true;
                DrawOnPricePanel = true;
                PaintPriceMarkers = true;
                IsSuspendedWhileInactive = false;

                Market = "Auto";
                Folder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "AlgoTraderLevels");
                MaxAgeMinutes = 60;

                AddPlot(new Stroke(Brushes.MediumSeaGreen, DashStyleHelper.Dash, 1), PlotStyle.Line, "OuterCallWall");
                AddPlot(new Stroke(Brushes.LimeGreen, 3), PlotStyle.Line, "CallWall");
                AddPlot(new Stroke(Brushes.Gold, DashStyleHelper.Dash, 2), PlotStyle.Line, "Flip");
                AddPlot(new Stroke(Brushes.Red, 3), PlotStyle.Line, "PutWall");
                AddPlot(new Stroke(Brushes.IndianRed, DashStyleHelper.Dash, 1), PlotStyle.Line, "OuterPutWall");
            }
            else if (State == State.DataLoaded)
            {
                string market = Market;
                if (string.IsNullOrWhiteSpace(market) || market.Equals("Auto", StringComparison.OrdinalIgnoreCase))
                {
                    string root = Instrument.MasterInstrument.Name.ToUpperInvariant();   // NQ, MNQ, ES, MES
                    market = root.EndsWith("NQ") ? "NQ" : root.EndsWith("ES") ? "ES" : root;
                }
                filePath = Path.Combine(Folder, market + ".csv");
                Load();
            }
        }

        protected override void OnBarUpdate()
        {
            if (State == State.Realtime && (DateTime.Now - lastCheck).TotalSeconds >= 20)
            {
                lastCheck = DateTime.Now;
                Load();
            }

            int i = LatestAtOrBefore(Time[0]);
            bool fresh = i >= 0 && (Time[0] - snaps[i].Time).TotalMinutes <= MaxAgeMinutes;
            for (int k = 0; k < 5; k++)
            {
                double v = fresh ? snaps[i].Levels[k] : double.NaN;
                if (double.IsNaN(v)) Values[k].Reset();
                else Values[k][0] = v;
            }
        }

        // Read the CSV again if it changed. Lines: time_utc,outer_call,call,flip,put,outer_put
        private void Load()
        {
            try
            {
                if (filePath == null || !File.Exists(filePath)) return;
                DateTime stamp = File.GetLastWriteTimeUtc(filePath);
                if (stamp == fileStamp) return;
                fileStamp = stamp;

                var fresh = new List<Snap>();
                TimeZoneInfo tz = NinjaTrader.Core.Globals.GeneralOptions.TimeZoneInfo;
                using (var fs = new FileStream(filePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                using (var reader = new StreamReader(fs))
                {
                    string line;
                    while ((line = reader.ReadLine()) != null)
                    {
                        string[] p = line.Split(',');
                        if (p.Length < 6 || p[0].StartsWith("time")) continue;
                        DateTime utc;
                        if (!DateTime.TryParseExact(p[0], "yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture,
                                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out utc)) continue;
                        var levels = new double[5];
                        for (int k = 0; k < 5; k++)
                        {
                            double v;
                            levels[k] = double.TryParse(p[k + 1], NumberStyles.Float, CultureInfo.InvariantCulture, out v) ? v : double.NaN;
                        }
                        fresh.Add(new Snap { Time = TimeZoneInfo.ConvertTimeFromUtc(DateTime.SpecifyKind(utc, DateTimeKind.Unspecified), tz), Levels = levels });
                    }
                }
                fresh.Sort((a, b) => a.Time.CompareTo(b.Time));
                snaps.Clear();
                snaps.AddRange(fresh);
            }
            catch (IOException)
            {
                // The script is writing right now: try again on the next check.
                fileStamp = DateTime.MinValue;
            }
        }

        private int LatestAtOrBefore(DateTime t)
        {
            int lo = 0, hi = snaps.Count - 1, found = -1;
            while (lo <= hi)
            {
                int mid = (lo + hi) / 2;
                if (snaps[mid].Time <= t) { found = mid; lo = mid + 1; }
                else hi = mid - 1;
            }
            return found;
        }

        #region Properties
        [NinjaScriptProperty]
        [Display(Name = "Market", Description = "Auto (from the chart), NQ or ES", Order = 1, GroupName = "Levels")]
        public string Market { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Folder", Description = "Where oi-walls.bat writes NQ.csv / ES.csv", Order = 2, GroupName = "Levels")]
        public string Folder { get; set; }

        [NinjaScriptProperty]
        [Range(5, 1440)]
        [Display(Name = "Hide after (minutes)", Description = "Stop drawing a level this long after its last refresh (no lines across nights)", Order = 3, GroupName = "Levels")]
        public int MaxAgeMinutes { get; set; }

        [Browsable(false)] [XmlIgnore] public Series<double> OuterCallWall { get { return Values[0]; } }
        [Browsable(false)] [XmlIgnore] public Series<double> CallWall { get { return Values[1]; } }
        [Browsable(false)] [XmlIgnore] public Series<double> Flip { get { return Values[2]; } }
        [Browsable(false)] [XmlIgnore] public Series<double> PutWall { get { return Values[3]; } }
        [Browsable(false)] [XmlIgnore] public Series<double> OuterPutWall { get { return Values[4]; } }
        #endregion
    }
}
