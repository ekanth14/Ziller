"""Prospective memory criteria: committed private memory versus resident pages."""
import statistics

PROTOCOL='phase3-private-memory-v2'
RULE='Second-half private absolute slope <=0.1 MiB/min, private range <=10 MiB, RSS growth slope <=0.1 MiB/min; RSS declines are reported, not classified as leaks'


def slope(rows,key):
    points=[(r['elapsed_seconds']/60,r[key]) for r in rows if r.get(key) is not None]
    if len(points)<2:return None
    x=statistics.mean(a for a,b in points);y=statistics.mean(b for a,b in points)
    denominator=sum((a-x)**2 for a,b in points)
    return sum((a-x)*(b-y) for a,b in points)/denominator if denominator else None


def memory_assessment(samples):
    tail=samples[len(samples)//2:]
    private=slope(tail,'private_mb');rss=slope(tail,'rss_mb')
    complete=bool(tail) and all(r.get('private_mb') is not None and r.get('rss_mb') is not None for r in tail)
    spread=max(r['private_mb'] for r in tail)-min(r['private_mb'] for r in tail) if complete else None
    private_flat=complete and private is not None and abs(private)<=.1 and spread<=10
    return dict(memory_protocol=PROTOCOL,memory_rule=RULE,
        private_slope_mb_per_minute=slope(samples,'private_mb'),
        private_tail_slope_mb_per_minute=private,private_tail_range_mb=spread,
        private_plateau=bool(private_flat),memory_accepted=bool(private_flat and rss is not None and rss<=.1))
