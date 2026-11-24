// LevelsPlus - one indicator on top of your two ama VWAPs (LizardIndicators amaCurrentDayVWAP /
// amaCurrentWeekVWAP) and NinjaTrader's Current Day OHL. It never changes those indicators.
//
// What it adds (each part can be switched off in the settings):
//   1. VWAP midbands  - halfway between the ama bands: +/-0.5, 1.5, 2.5 SD, for the Day and Week VWAP.
//                       Read straight from the ama indicators, so they sit exactly between their bands.
//   2. MTF daily band - CME day open (6 PM ET) +/- 1 to 1.5 SDEV. SDEV = standard deviation of the
//                       % net change (open to close) of the last 20 CME days. No center line: your
//                       Current Day OHL already draws the open.
//   3. ALN session band - session open +/- 0.5 to 1 SDEV (last 20 sessions), only while the session
//                       runs: Asia 8 PM-2 AM, London 2-8 AM, AM 8 AM-12 PM, PM 12-4 PM (New York time).
//   4. TBR bands      - two bands per session: open + 0.25 SDEV out to the usual overshoot (the
//                       stretch median, about 0.41) and the same below. SDEV here is the sample one
//                       (like the ALN TBR code). First touch gets a "TBR hit 5:30 AM" tag.
//   5. Labels         - each band's name written inside it at the right edge, and a tag (top right)
//                       saying which Day / Week VWAP band price is in right now.
//
// The session math runs on a 1-minute series this indicator loads itself, so the levels are the
// same on any chart timeframe. Load at least 30 days of data so 20 full days / sessions exist.
//
// Install: copy to  Documents\NinjaTrader 8\bin\Custom\Indicators\  then New > NinjaScript Editor,
// press F5. Your ama VWAP indicators must be installed (they are used, not changed).
// Before installing: Tools > Export > NinjaScript Add-On to back up what you have.
// Read-only: it never places, changes or cancels orders.
#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class LevelsPlus : Indicator
    {
        // One running session (the CME day, or an ALN session), tracked on 1-minute bars.
        private class Session
        {
            public string Name;            // "MTF D", "Asia", "London", "AM", "PM"
            public int StartMin;           // New York minutes after midnight
            public int Length;             // minutes
            public double StretchMedian;   // TBR band outer edge, in SDEV
            public readonly List<double> History = new List<double>();   // % net change of finished sessions
            public DateTime Key = DateTime.MinValue;   // New York date the session started
            public bool Active;
            public DateTime Start;         // chart time of the first minute
            public double Open, Close;
            public int Count;
            public double SdPop = double.NaN, SdSample = double.NaN;
            public bool TbrHit;
        }

        private Session day;
        private readonly List<Session> aln = new List<Session>();
        private TimeZoneInfo chartTz, nyTz;
        private LizardIndicators.amaCurrentDayVWAP dayVwap;
        private LizardIndicators.amaCurrentWeekVWAP weekVwap;
        private SimpleFont labelFont, tagFont;
        private Brush dayLabelBrush, weekLabelBrush, tagBackBrush;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Midbands for the ama Day / Week VWAP, plus MTF SDEV, ALN SDEV and ALN TBR drawn as light bands right in price.";
                Name = "LevelsPlus";
                Calculate = Calculate.OnPriceChange;
                IsOverlay = true;
                DisplayInDataBox = true;
                DrawOnPricePanel = true;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = true;
                BarsRequiredToPlot = 0;

                // ama settings: keep these the same as your ama indicators
                DaySessionType = amaSessionTypeVWAPD.Full_Session;
                DayTimeZone = amaTimeZonesVWAPD.Exchange_Time;
                WeekSessionType = amaSessionTypeVWAPW.Full_Session;
                WeekTimeZone = amaTimeZonesVWAPW.Exchange_Time;
                CustomStart = "15:15";
                CustomEnd = "08:30";
                Sd1 = 1; Sd2 = 2; Sd3 = 3;

                ShowDayMidbands = true;
                ShowWeekMidbands = true;
                ShowMtf = true;
                ShowAlnAsia = false;
                ShowAlnLondon = false;
                ShowAlnAm = true;
                ShowAlnPm = true;
                ShowTbr = true;
                ShowLabels = true;
                ShowPriceTag = true;
                Lookback = 20;

                MtfBrush = MakeBrush(60, 207, 154);
                AlnBrush = MakeBrush(201, 162, 255);
                TbrBrush = MakeBrush(255, 181, 71);
                MtfOpacity = 14;
                AlnOpacity = 16;
                TbrOpacity = 24;

                Brush dayDots = MakeBrush(111, 136, 255);
                Brush weekDots = MakeBrush(154, 166, 178);
                AddPlot(new Stroke(dayDots, DashStyleHelper.Dot, 1), PlotStyle.Line, "Day mid +2.5");
                AddPlot(new Stroke(dayDots, DashStyleHelper.Dot, 1), PlotStyle.Line, "Day mid +1.5");
                AddPlot(new Stroke(dayDots, DashStyleHelper.Dot, 1), PlotStyle.Line, "Day mid +0.5");
                AddPlot(new Stroke(dayDots, DashStyleHelper.Dot, 1), PlotStyle.Line, "Day mid -0.5");
                AddPlot(new Stroke(dayDots, DashStyleHelper.Dot, 1), PlotStyle.Line, "Day mid -1.5");
                AddPlot(new Stroke(dayDots, DashStyleHelper.Dot, 1), PlotStyle.Line, "Day mid -2.5");
                AddPlot(new Stroke(weekDots, DashStyleHelper.Dot, 1), PlotStyle.Line, "Week mid +2.5");
                AddPlot(new Stroke(weekDots, DashStyleHelper.Dot, 1), PlotStyle.Line, "Week mid +1.5");
                AddPlot(new Stroke(weekDots, DashStyleHelper.Dot, 1), PlotStyle.Line, "Week mid +0.5");
                AddPlot(new Stroke(weekDots, DashStyleHelper.Dot, 1), PlotStyle.Line, "Week mid -0.5");
                AddPlot(new Stroke(weekDots, DashStyleHelper.Dot, 1), PlotStyle.Line, "Week mid -1.5");
                AddPlot(new Stroke(weekDots, DashStyleHelper.Dot, 1), PlotStyle.Line, "Week mid -2.5");
            }
            else if (State == State.Configure)
            {
                AddDataSeries(BarsPeriodType.Minute, 1);
            }
            else if (State == State.DataLoaded)
            {
                dayVwap = amaCurrentDayVWAP(DaySessionType, amaBandTypeVWAPD.Standard_Deviation, DayTimeZone, CustomStart, CustomEnd, Sd1, Sd2, Sd3, 1, 2, 3);
                weekVwap = amaCurrentWeekVWAP(WeekSessionType, amaBandTypeVWAPW.Standard_Deviation, WeekTimeZone, CustomStart, CustomEnd, Sd1, Sd2, Sd3, 1, 2, 3);

                chartTz = NinjaTrader.Core.Globals.GeneralOptions.TimeZoneInfo;
                nyTz = TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");
                labelFont = new SimpleFont("Arial", 10) { Bold = true };
                tagFont = new SimpleFont("Arial", 11) { Bold = true };
                dayLabelBrush = MakeBrush(195, 155, 255);
                weekLabelBrush = MakeBrush(184, 194, 204);
                tagBackBrush = MakeBrush(43, 45, 49);

                day = new Session { Name = "MTF D", StartMin = 18 * 60, Length = 23 * 60 };
                aln.Clear();
                if (ShowAlnAsia) aln.Add(new Session { Name = "Asia", StartMin = 20 * 60, Length = 360, StretchMedian = 0.409 });
                if (ShowAlnLondon) aln.Add(new Session { Name = "London", StartMin = 2 * 60, Length = 360, StretchMedian = 0.397 });
                if (ShowAlnAm) aln.Add(new Session { Name = "AM", StartMin = 8 * 60, Length = 240, StretchMedian = 0.408 });
                if (ShowAlnPm) aln.Add(new Session { Name = "PM", StartMin = 12 * 60, Length = 240, StretchMedian = 0.401 });
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress == 0)
                UpdateMidbands();
            else if (BarsInProgress == 1 && IsFirstTickOfBar && CurrentBars[1] > 0)
                OnMinuteClosed();   // the previous 1-minute bar just finished
        }

        // ---- 1. midbands, labels on the VWAP bands, price tag (chart series) ------------------------
        private void UpdateMidbands()
        {
            if (CurrentBar < 1 || dayVwap == null || weekVwap == null) return;
            bool dayOk = dayVwap.UpperBand3.IsValidDataPoint(0) && dayVwap.LowerBand3.IsValidDataPoint(0);
            bool weekOk = weekVwap.UpperBand3.IsValidDataPoint(0) && weekVwap.LowerBand3.IsValidDataPoint(0);

            if (ShowDayMidbands && dayOk)
                SetMids(0, dayVwap.SessionVWAP[0], dayVwap.UpperBand1[0], dayVwap.UpperBand2[0], dayVwap.UpperBand3[0], dayVwap.LowerBand1[0], dayVwap.LowerBand2[0], dayVwap.LowerBand3[0]);
            if (ShowWeekMidbands && weekOk)
                SetMids(6, weekVwap.SessionVWAP[0], weekVwap.UpperBand1[0], weekVwap.UpperBand2[0], weekVwap.UpperBand3[0], weekVwap.LowerBand1[0], weekVwap.LowerBand2[0], weekVwap.LowerBand3[0]);

            if (ShowPriceTag && State == State.Realtime && (dayOk || weekOk))
            {
                string text = "Price " + Close[0].ToString("N2");
                if (dayOk) text += "   in D VWAP " + Zone(Close[0], dayVwap.SessionVWAP[0], dayVwap.UpperBand1[0]);
                if (weekOk) text += "   |   W VWAP " + Zone(Close[0], weekVwap.SessionVWAP[0], weekVwap.UpperBand1[0]);
                Draw.TextFixed(this, "LP_now", text, TextPosition.TopRight, Brushes.White, tagFont, Brushes.Transparent, tagBackBrush, 70);
            }

            if (!IsFirstTickOfBar) return;   // labels move once per bar
            if (ShowLabels && dayOk)
            {
                Label("LP_dU", "D VWAP +2-3 SD", (dayVwap.UpperBand2[0] + dayVwap.UpperBand3[0]) / 2, Time[0], dayLabelBrush);
                Label("LP_dL", "D VWAP -2-3 SD", (dayVwap.LowerBand2[0] + dayVwap.LowerBand3[0]) / 2, Time[0], dayLabelBrush);
            }
            if (ShowLabels && weekOk)
            {
                Label("LP_wU", "W VWAP +2-3 SD", (weekVwap.UpperBand2[0] + weekVwap.UpperBand3[0]) / 2, Time[0], weekLabelBrush);
                Label("LP_wL", "W VWAP -2-3 SD", (weekVwap.LowerBand2[0] + weekVwap.LowerBand3[0]) / 2, Time[0], weekLabelBrush);
            }
        }

        private void SetMids(int first, double vwap, double u1, double u2, double u3, double l1, double l2, double l3)
        {
            Values[first + 0][0] = (u2 + u3) / 2;
            Values[first + 1][0] = (u1 + u2) / 2;
            Values[first + 2][0] = (vwap + u1) / 2;
            Values[first + 3][0] = (vwap + l1) / 2;
            Values[first + 4][0] = (l1 + l2) / 2;
            Values[first + 5][0] = (l2 + l3) / 2;
        }

        // Which band price is in, in SD from the VWAP, e.g. "+0.5 to +1" or "-0.5 to +0.5".
        private string Zone(double price, double vwap, double upper1)
        {
            double unit = (upper1 - vwap) / Sd1;
            if (unit <= 0) return "";
            double k = (price - vwap) / unit;
            if (Math.Abs(k) < 0.5) return "-0.5 to +0.5";
            double a = Math.Floor(Math.Abs(k) * 2) / 2;   // 0.5 steps
            if (a >= 3) return k > 0 ? "above +3" : "below -3";
            string sign = k > 0 ? "+" : "-";
            return sign + a.ToString("0.#") + " to " + sign + (a + 0.5).ToString("0.#");
        }

        // ---- 2-4. sessions on the 1-minute series ----------------------------------------------------
        private void OnMinuteClosed()
        {
            DateTime barEnd = Times[1][1];
            DateTime barStart = barEnd.AddMinutes(-1);
            DateTime ny = TimeZoneInfo.ConvertTime(barStart, chartTz, nyTz);
            int nyMin = ny.Hour * 60 + ny.Minute;
            double o = Opens[1][1], h = Highs[1][1], l = Lows[1][1], c = Closes[1][1];

            Step(day, ny, nyMin, barStart, barEnd, o, h, l, c, true);
            foreach (Session s in aln)
                Step(s, ny, nyMin, barStart, barEnd, o, h, l, c, false);
        }

        private void Step(Session s, DateTime ny, int nyMin, DateTime barStart, DateTime barEnd, double o, double h, double l, double c, bool isDay)
        {
            int offset = ((nyMin - s.StartMin) % 1440 + 1440) % 1440;
            bool inside = offset < s.Length && (isDay || ny.DayOfWeek != DayOfWeek.Saturday);
            if (!inside)
            {
                if (s.Active) Finish(s);
                return;
            }
            DateTime key = ny.AddMinutes(-offset).Date;
            if (!s.Active || key != s.Key)
            {
                if (s.Active) Finish(s);
                s.Active = true;
                s.Key = key;
                s.Start = barStart;
                s.Open = o;
                s.Count = 0;
                s.TbrHit = false;
                s.SdPop = Sd(s.History, false);
                s.SdSample = Sd(s.History, true);
                if (offset > 5) s.SdPop = s.SdSample = double.NaN;   // joined late: don't draw a wrong open
                if (!double.IsNaN(s.SdPop)) DrawBands(s, isDay);
            }
            s.Close = c;
            s.Count++;

            if (!double.IsNaN(s.SdPop))
            {
                if (ShowLabels) DrawLabels(s, isDay, barEnd);
                if (!isDay && ShowTbr && !s.TbrHit)
                {
                    double pts = s.Open * s.SdSample / 100;
                    double up = s.Open + 0.25 * pts, dn = s.Open - 0.25 * pts;
                    if (h >= up || l <= dn)
                    {
                        s.TbrHit = true;
                        bool upSide = h >= up && (l > dn || Math.Abs(o - up) <= Math.Abs(o - dn));
                        Draw.Text(this, "LP_tbrhit_" + s.Name + Stamp(s), false, "TBR hit " + barStart.ToString("h:mm tt"),
                            barStart, upSide ? up : dn, upSide ? 12 : -12, TbrBrush, tagFont, TextAlignment.Left, Brushes.Transparent, Brushes.Transparent, 0);
                    }
                }
            }
        }

        private void Finish(Session s)
        {
            if (s.Count >= 0.83 * s.Length && s.Open > 0)
            {
                s.History.Add((s.Close - s.Open) / s.Open * 100);
                if (s.History.Count > 200) s.History.RemoveAt(0);
            }
            s.Active = false;
        }

        private double Sd(List<double> values, bool sample)
        {
            int n = Lookback;
            if (values.Count < n) return double.NaN;
            double mean = 0;
            for (int i = values.Count - n; i < values.Count; i++) mean += values[i];
            mean /= n;
            double ss = 0;
            for (int i = values.Count - n; i < values.Count; i++) ss += (values[i] - mean) * (values[i] - mean);
            return Math.Sqrt(ss / (sample ? n - 1 : n));
        }

        private string Stamp(Session s) { return s.Key.ToString("yyyyMMdd"); }

        private void DrawBands(Session s, bool isDay)
        {
            DateTime end = s.Start.AddMinutes(s.Length);
            double pts = s.Open * s.SdPop / 100;
            string id = "LP_" + s.Name + "_" + Stamp(s);
            if (isDay && ShowMtf)
            {
                Band(id + "_up", s.Start, end, s.Open + 1.0 * pts, s.Open + 1.5 * pts, MtfBrush, MtfOpacity);
                Band(id + "_dn", s.Start, end, s.Open - 1.5 * pts, s.Open - 1.0 * pts, MtfBrush, MtfOpacity);
            }
            if (!isDay)
            {
                Band(id + "_up", s.Start, end, s.Open + 0.5 * pts, s.Open + 1.0 * pts, AlnBrush, AlnOpacity);
                Band(id + "_dn", s.Start, end, s.Open - 1.0 * pts, s.Open - 0.5 * pts, AlnBrush, AlnOpacity);
                if (ShowTbr)
                {
                    double tp = s.Open * s.SdSample / 100;
                    Band(id + "_tbrU", s.Start, end, s.Open + 0.25 * tp, s.Open + s.StretchMedian * tp, TbrBrush, TbrOpacity);
                    Band(id + "_tbrD", s.Start, end, s.Open - s.StretchMedian * tp, s.Open - 0.25 * tp, TbrBrush, TbrOpacity);
                }
            }
        }

        // Names written inside the bands, kept at the newest bar so they sit next to price.
        private void DrawLabels(Session s, bool isDay, DateTime at)
        {
            double pts = s.Open * s.SdPop / 100;
            string id = "LP_lbl_" + s.Name;   // one label per kind: it moves along with the bars
            if (isDay && ShowMtf)
            {
                Label(id + "_up", "MTF D +1 to +1.5", s.Open + 1.25 * pts, at, MtfBrush);
                Label(id + "_dn", "MTF D -1 to -1.5", s.Open - 1.25 * pts, at, MtfBrush);
            }
            if (!isDay)
            {
                Label(id + "_up", "ALN " + s.Name + " +0.5 to +1", s.Open + 0.75 * pts, at, AlnBrush);
                Label(id + "_dn", "ALN " + s.Name + " -0.5 to -1", s.Open - 0.75 * pts, at, AlnBrush);
                if (ShowTbr)
                {
                    double tp = s.Open * s.SdSample / 100;
                    double mid = (0.25 + s.StretchMedian) / 2;
                    Label(id + "_tbrU", "TBR " + s.Name + " +0.25", s.Open + mid * tp, at, TbrBrush);
                    Label(id + "_tbrD", "TBR " + s.Name + " -0.25", s.Open - mid * tp, at, TbrBrush);
                }
            }
        }

        private void Band(string tag, DateTime start, DateTime end, double lo, double hi, Brush brush, int opacity)
        {
            Draw.Rectangle(this, tag, false, start, hi, end, lo, Brushes.Transparent, brush, opacity);
        }

        private void Label(string tag, string text, double y, DateTime at, Brush brush)
        {
            Draw.Text(this, tag, false, text, at, y, 0, brush, labelFont, TextAlignment.Right, Brushes.Transparent, Brushes.Transparent, 0);
        }

        private static Brush MakeBrush(byte r, byte g, byte b)
        {
            var brush = new SolidColorBrush(Color.FromRgb(r, g, b));
            brush.Freeze();
            return brush;
        }

        #region Properties
        [NinjaScriptProperty]
        [Display(Name = "Day VWAP session", Description = "Same as your amaCurrentDayVWAP", Order = 1, GroupName = "1. Your ama VWAP settings")]
        public amaSessionTypeVWAPD DaySessionType { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Day VWAP time zone", Order = 2, GroupName = "1. Your ama VWAP settings")]
        public amaTimeZonesVWAPD DayTimeZone { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Week VWAP session", Description = "Same as your amaCurrentWeekVWAP", Order = 3, GroupName = "1. Your ama VWAP settings")]
        public amaSessionTypeVWAPW WeekSessionType { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Week VWAP time zone", Order = 4, GroupName = "1. Your ama VWAP settings")]
        public amaTimeZonesVWAPW WeekTimeZone { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Custom start (h:mm)", Description = "Only used with Custom_Hours", Order = 5, GroupName = "1. Your ama VWAP settings")]
        public string CustomStart { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Custom end (h:mm)", Description = "Only used with Custom_Hours", Order = 6, GroupName = "1. Your ama VWAP settings")]
        public string CustomEnd { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 10)]
        [Display(Name = "SD multiplier 1", Order = 7, GroupName = "1. Your ama VWAP settings")]
        public double Sd1 { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 10)]
        [Display(Name = "SD multiplier 2", Order = 8, GroupName = "1. Your ama VWAP settings")]
        public double Sd2 { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 10)]
        [Display(Name = "SD multiplier 3", Order = 9, GroupName = "1. Your ama VWAP settings")]
        public double Sd3 { get; set; }

        [Display(Name = "Day midbands", Order = 1, GroupName = "2. What to show")]
        public bool ShowDayMidbands { get; set; }

        [Display(Name = "Week midbands", Order = 2, GroupName = "2. What to show")]
        public bool ShowWeekMidbands { get; set; }

        [Display(Name = "MTF daily band (+/-1 to 1.5)", Order = 3, GroupName = "2. What to show")]
        public bool ShowMtf { get; set; }

        [Display(Name = "ALN Asia (8 PM-2 AM NY)", Order = 4, GroupName = "2. What to show")]
        public bool ShowAlnAsia { get; set; }

        [Display(Name = "ALN London (2-8 AM NY)", Order = 5, GroupName = "2. What to show")]
        public bool ShowAlnLondon { get; set; }

        [Display(Name = "ALN AM (8 AM-12 PM NY)", Order = 6, GroupName = "2. What to show")]
        public bool ShowAlnAm { get; set; }

        [Display(Name = "ALN PM (12-4 PM NY)", Order = 7, GroupName = "2. What to show")]
        public bool ShowAlnPm { get; set; }

        [Display(Name = "TBR bands (+0.25 / -0.25)", Order = 8, GroupName = "2. What to show")]
        public bool ShowTbr { get; set; }

        [Display(Name = "Labels inside the bands", Order = 9, GroupName = "2. What to show")]
        public bool ShowLabels { get; set; }

        [Display(Name = "'Price is in' tag (top right)", Order = 10, GroupName = "2. What to show")]
        public bool ShowPriceTag { get; set; }

        [Range(5, 100)]
        [Display(Name = "Lookback (days / sessions)", Description = "How many past days or sessions make 1 SDEV", Order = 11, GroupName = "2. What to show")]
        public int Lookback { get; set; }

        [XmlIgnore]
        [Display(Name = "MTF band color", Order = 1, GroupName = "3. Colors")]
        public Brush MtfBrush { get; set; }
        [Browsable(false)]
        public string MtfBrushSerialize { get { return Serialize.BrushToString(MtfBrush); } set { MtfBrush = Serialize.StringToBrush(value); } }

        [Range(0, 100)]
        [Display(Name = "MTF band opacity %", Order = 2, GroupName = "3. Colors")]
        public int MtfOpacity { get; set; }

        [XmlIgnore]
        [Display(Name = "ALN band color", Order = 3, GroupName = "3. Colors")]
        public Brush AlnBrush { get; set; }
        [Browsable(false)]
        public string AlnBrushSerialize { get { return Serialize.BrushToString(AlnBrush); } set { AlnBrush = Serialize.StringToBrush(value); } }

        [Range(0, 100)]
        [Display(Name = "ALN band opacity %", Order = 4, GroupName = "3. Colors")]
        public int AlnOpacity { get; set; }

        [XmlIgnore]
        [Display(Name = "TBR band color", Order = 5, GroupName = "3. Colors")]
        public Brush TbrBrush { get; set; }
        [Browsable(false)]
        public string TbrBrushSerialize { get { return Serialize.BrushToString(TbrBrush); } set { TbrBrush = Serialize.StringToBrush(value); } }

        [Range(0, 100)]
        [Display(Name = "TBR band opacity %", Order = 6, GroupName = "3. Colors")]
        public int TbrOpacity { get; set; }
        #endregion
    }
}
