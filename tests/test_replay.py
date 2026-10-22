from pathlib import Path
from strategy_lab.replay import replay
from strategy_lab.targets import OrderBlock, choose_target

ROOT=Path(__file__).resolve().parents[1]/'sample_data'

def test_sample_replay_target_before_ob():
    trade=replay(ROOT/'candles.csv',ROOT/'signals.csv',ROOT/'blocks.csv')[0]
    assert trade.outcome=='TARGET'
    assert trade.target < 100900
    assert trade.gross_rr < 2

def test_partial_touch_remains_valid():
    d=choose_target(entry=100,stop=99,side='long',blocks=[OrderBlock(101,102,'bearish',1)],as_of=2)
    assert d.accepted and d.target < 101

def test_wick_invalidation_known_before_signal_ignored():
    d=choose_target(entry=100,stop=99,side='long',blocks=[OrderBlock(101,102,'bearish',1,2)],as_of=3)
    assert d.target==102
