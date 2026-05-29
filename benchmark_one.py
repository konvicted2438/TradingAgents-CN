"""
跑一次 TradingAgents propagate，测耗时 + 各节点细分耗时。
用 LM Studio @ 127.0.0.1:1234 作为 LLM 后端。

用法:
  python benchmark_one.py                       # 默认: 000300, 昨天
  python benchmark_one.py NVDA 2024-05-10       # 自定义标的+日期
"""
import os
import sys
import time
import datetime as dt

# 强制 .env 装载（脚本可能不通过框架启动器跑）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# LM Studio 不校验 key 但 langchain-openai 需要个非空 key
os.environ.setdefault("CUSTOM_OPENAI_API_KEY", "lm-studio")
os.environ.setdefault("OPENAI_API_KEY", "lm-studio")

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else "510300"  # 沪深300ETF（指数 000300 数据源不接）
    date   = sys.argv[2] if len(sys.argv) > 2 else (dt.date.today() - dt.timedelta(days=1)).strftime("%Y-%m-%d")

    config = DEFAULT_CONFIG.copy()
    # —— DeepSeek API ——
    config["llm_provider"]   = "deepseek"
    config["backend_url"]    = "https://api.deepseek.com"
    config["deep_think_llm"] = "deepseek-chat"   # V3，便宜 + 快；不够再升 deepseek-reasoner
    config["quick_think_llm"]= "deepseek-chat"

    # —— 最快配置：辩论 1 轮 + 关闭在线工具 ——
    config["max_debate_rounds"]       = 1
    config["max_risk_discuss_rounds"] = 1
    config["online_tools"]            = False
    config["max_recur_limit"]         = 50


    print("=" * 60)
    print(f"Ticker:    {ticker}")
    print(f"Date:      {date}")
    print(f"LLM:       {config['deep_think_llm']} @ {config['backend_url']}")
    print(f"Debate:    {config['max_debate_rounds']} round")
    print("=" * 60)

    print("\n初始化 TradingAgentsGraph...")
    t_init = time.time()
    ta = TradingAgentsGraph(debug=True, config=config)
    print(f"  初始化耗时: {time.time() - t_init:.2f}s\n")

    print("propagate 开始...\n")
    t0 = time.time()
    try:
        final_state, decision = ta.propagate(ticker, date)
    except Exception as e:
        elapsed = time.time() - t0
        print(f"\n❌ propagate 失败 (耗时 {elapsed:.1f}s)")
        import traceback
        traceback.print_exc()
        return

    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print(f"✅ propagate 完成  总耗时: {elapsed:.1f}s  ({elapsed/60:.1f}min)")
    print("=" * 60)
    print("\n【最终决策】")
    print(decision)


if __name__ == "__main__":
    main()
