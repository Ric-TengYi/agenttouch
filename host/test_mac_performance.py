import unittest
from types import SimpleNamespace as N
from mac_performance import Collector

class Backend:
    step=0
    def cpu_times(self):return N(user=20+self.step*1,system=10+self.step*1,idle=70+self.step*2,nice=0)
    def virtual_memory(self):return N(total=1000,available=400)
    def disk_usage(self,p):return N(total=2000,free=500)
    def disk_io_counters(self):return N(read_bytes=100+self.step*200,write_bytes=100+self.step*100)
    def net_io_counters(self,pernic=True):return {'en0':N(bytes_recv=100+self.step*400,bytes_sent=100+self.step*200), 'lo0':N(bytes_recv=999999,bytes_sent=999999)}
    def net_if_stats(self):return {'en0':N(isup=True),'lo0':N(isup=True)}

class PerfTests(unittest.TestCase):
    def test_first_sample_unknown_then_real_counter_rates(self):
        b=Backend();c=Collector(b)
        first=c.sample(100,10)
        self.assertIsNone(first['cpu_pct']);self.assertIsNone(first['net_rx'])
        b.step=1;s=c.sample(102,12)
        self.assertEqual(s['cpu_pct'],50)
        self.assertEqual(s['memory_pct'],60)
        self.assertEqual(s['net_rx'],200)
        self.assertEqual(s['disk_write'],50)
    def test_resume_gap_and_reset_do_not_make_fake_rates(self):
        b=Backend();c=Collector(b);c.sample(100,10);b.step=1
        s=c.sample(150,12);self.assertIsNone(s['cpu_pct']);self.assertIsNone(s['net_rx'])
        b.step=0;s=c.sample(152,14);self.assertIsNone(s['net_rx'])
    def test_missing_metric_keeps_other_readings(self):
        b=Backend();b.disk_io_counters=lambda:None;c=Collector(b)
        c.sample(100,10);b.step=1;s=c.sample(102,12)
        self.assertEqual(s['cpu_pct'],50);self.assertIsNone(s['disk_read'])
        self.assertEqual(s['memory_pct'],60)
