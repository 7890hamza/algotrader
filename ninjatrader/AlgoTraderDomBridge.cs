// AlgoTrader DOM bridge for NinjaTrader 8.
//
// Streams this chart's order book (market depth) and every trade to the AlgoTrader
// DOM service (dom-service, TCP port 8060 on this PC). Read-only: it never sends,
// changes or cancels orders.
//
// Install: copy this file to
//   Documents\NinjaTrader 8\bin\Custom\Indicators\
// then in NinjaTrader: New > NinjaScript Editor > press F5 (compile).
// Use: open an ES chart (any timeframe), add the "AlgoTraderDomBridge" indicator.
// It only streams in real time and needs your NinjaTrader market depth (Level 2) data.
//
// Wire format, one JSON object per line (times in epoch ms, UTC):
//   {"k":"hello","sym":"ES 12-26","tick":0.25}
//   {"k":"reset"}                                   the book should be cleared
//   {"k":"d","t":..,"s":"b","p":7443.25,"v":96}    size now resting at a price (0 = gone)
//   {"k":"q","t":..,"b":7443.25,"a":7443.5}        best bid / ask
//   {"k":"x","t":..,"p":7443.5,"v":3,"s":"buy"}    a trade (buy = lifted the ask)
#region Using declarations
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class AlgoTraderDomBridge : Indicator
    {
        private readonly List<double[]> bidRows = new List<double[]>();   // by position: [price, volume]
        private readonly List<double[]> askRows = new List<double[]>();
        private readonly Dictionary<double, long> bidSent = new Dictionary<double, long>();
        private readonly Dictionary<double, long> askSent = new Dictionary<double, long>();
        private BlockingCollection<string> outbox;
        private Thread sender;
        private volatile bool running;
        private double lastBid, lastAsk;

        [NinjaScriptProperty]
        [Display(Name = "Host", Order = 1, GroupName = "AlgoTrader")]
        public string Host { get; set; }

        [NinjaScriptProperty]
        [Range(1, 65535)]
        [Display(Name = "Port", Order = 2, GroupName = "AlgoTrader")]
        public int Port { get; set; }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "AlgoTraderDomBridge";
                Description = "Streams this instrument's DOM and trades to the AlgoTrader memory DOM (read-only).";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = false;
                Host = "127.0.0.1";
                Port = 8060;
            }
            else if (State == State.Realtime)
            {
                outbox = new BlockingCollection<string>(new ConcurrentQueue<string>(), 200000);
                running = true;
                sender = new Thread(SendLoop) { IsBackground = true, Name = "AlgoTraderDomBridge" };
                sender.Start();
            }
            else if (State == State.Terminated)
            {
                running = false;
                if (outbox != null) outbox.CompleteAdding();
            }
        }

        protected override void OnBarUpdate() { }

        private static long Ms(DateTime t)
        {
            return (long)(t.ToUniversalTime() - new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc)).TotalMilliseconds;
        }

        private static string Num(double v)
        {
            return v.ToString("0.########", CultureInfo.InvariantCulture);
        }

        private void Post(string line)
        {
            if (outbox == null || outbox.IsAddingCompleted) return;
            outbox.TryAdd(line);  // drops when the app is down for a long time; the book resyncs
        }

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            if (State != State.Realtime) return;
            bool bid = e.MarketDataType == MarketDataType.Bid;
            List<double[]> rows = bid ? bidRows : askRows;
            int pos = e.Position;
            if (e.Operation == Operation.Add)
            {
                if (pos > rows.Count) pos = rows.Count;
                rows.Insert(pos, new[] { e.Price, (double)e.Volume });
            }
            else if (e.Operation == Operation.Update)
            {
                if (pos < rows.Count) rows[pos] = new[] { e.Price, (double)e.Volume };
            }
            else if (e.Operation == Operation.Remove)
            {
                if (pos < rows.Count) rows.RemoveAt(pos);
            }
            Diff(bid, Ms(e.Time));
        }

        // Send only the prices whose resting size changed (positions shift as the book moves).
        private void Diff(bool bid, long t)
        {
            List<double[]> rows = bid ? bidRows : askRows;
            Dictionary<double, long> sent = bid ? bidSent : askSent;
            var now = new Dictionary<double, long>();
            foreach (double[] r in rows) now[r[0]] = (long)r[1];
            string s = bid ? "b" : "a";
            foreach (KeyValuePair<double, long> kv in now)
            {
                long old;
                if (!sent.TryGetValue(kv.Key, out old) || old != kv.Value)
                    Post("{\"k\":\"d\",\"t\":" + t + ",\"s\":\"" + s + "\",\"p\":" + Num(kv.Key) + ",\"v\":" + kv.Value + "}");
            }
            foreach (KeyValuePair<double, long> kv in sent)
                if (!now.ContainsKey(kv.Key))
                    Post("{\"k\":\"d\",\"t\":" + t + ",\"s\":\"" + s + "\",\"p\":" + Num(kv.Key) + ",\"v\":0}");
            sent.Clear();
            foreach (KeyValuePair<double, long> kv in now) sent[kv.Key] = kv.Value;
        }

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (State != State.Realtime) return;
            long t = Ms(e.Time);
            if (e.MarketDataType == MarketDataType.Last)
            {
                string side = e.Price >= e.Ask && e.Ask > 0 ? "buy" : e.Price <= e.Bid && e.Bid > 0 ? "sell" : "mid";
                Post("{\"k\":\"x\",\"t\":" + t + ",\"p\":" + Num(e.Price) + ",\"v\":" + e.Volume + ",\"s\":\"" + side + "\"}");
            }
            else if (e.MarketDataType == MarketDataType.Bid || e.MarketDataType == MarketDataType.Ask)
            {
                double b = e.MarketDataType == MarketDataType.Bid ? e.Price : lastBid;
                double a = e.MarketDataType == MarketDataType.Ask ? e.Price : lastAsk;
                if (b == lastBid && a == lastAsk) return;
                lastBid = b;
                lastAsk = a;
                Post("{\"k\":\"q\",\"t\":" + t + ",\"b\":" + Num(b) + ",\"a\":" + Num(a) + "}");
            }
        }

        // Runs on its own thread so NinjaTrader never waits on the network.
        private void SendLoop()
        {
            while (running)
            {
                try
                {
                    using (var client = new TcpClient())
                    {
                        client.NoDelay = true;
                        client.Connect(Host, Port);
                        using (NetworkStream net = client.GetStream())
                        {
                            Write(net, "{\"k\":\"hello\",\"sym\":\"" + Instrument.FullName + "\",\"tick\":" + Num(TickSize) + "}");
                            // a fresh connection gets the whole book again (anything queued is stale)
                            string line;
                            while (outbox.TryTake(out line)) { }
                            Write(net, "{\"k\":\"reset\"}");
                            TriggerCustomEvent(o => { bidSent.Clear(); askSent.Clear(); Diff(true, Ms(DateTime.UtcNow)); Diff(false, Ms(DateTime.UtcNow)); }, null);
                            while (running)
                            {
                                if (outbox.TryTake(out line, 1000)) Write(net, line);
                                else Write(net, "{\"k\":\"ping\"}");
                            }
                        }
                    }
                }
                catch (Exception)
                {
                    // the app is not running yet, or the connection dropped: try again shortly
                    Thread.Sleep(3000);
                }
            }
        }

        private static void Write(NetworkStream net, string line)
        {
            byte[] bytes = Encoding.UTF8.GetBytes(line + "\n");
            net.Write(bytes, 0, bytes.Length);
        }
    }
}
