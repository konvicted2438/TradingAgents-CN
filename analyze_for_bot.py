"""
TradingAgents-CN 桥接给 Telegram bot 用。
- 接 ticker + date，跑 propagate
- 把核心结果（决策 + 关键 analyst 报告摘要 + 耗时）写成 JSON
- 在另一个 conda env 里运行(tradingagents)，被 bot (gtaa env) 子进程调用

用法:
  python analyze_for_bot.py 510300 [2026-05-28] [/tmp/out.json]
退出码:
  0 = 成功
  非0 = 失败 (stderr 有原因)
"""
import os
import sys
import json
import time
import datetime as dt
import traceback

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

os.environ.setdefault("CUSTOM_OPENAI_API_KEY", "lm-studio")
os.environ.setdefault("OPENAI_API_KEY", "lm-studio")

import patches
patches.apply_all()

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG


def _config():
    cfg = DEFAULT_CONFIG.copy()
    cfg["llm_provider"]   = "deepseek"
    cfg["backend_url"]    = "https://api.deepseek.com"
    cfg["deep_think_llm"] = "deepseek-chat"
    cfg["quick_think_llm"]= "deepseek-chat"
    cfg["max_debate_rounds"]       = 1
    cfg["max_risk_discuss_rounds"] = 1
    cfg["online_tools"]            = False
    cfg["max_recur_limit"]         = 50
    return cfg


def _truncate(text, limit=600):
    if not text or not isinstance(text, str):
        return ""
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + "..."


def _extract_reports(final_state):
    """从 final_state 提取各 analyst 报告摘要。键名按框架的约定。"""
    if not isinstance(final_state, dict):
        return {}
    keys_of_interest = [
        ("market_report", "市场分析"),
        ("sentiment_report", "情绪/社媒分析"),
        ("news_report", "新闻分析"),
        ("fundamentals_report", "基本面分析"),
        ("investment_plan", "研究经理整合"),
        ("trader_investment_plan", "交易员投资计划"),
        ("final_trade_decision", "最终决策"),
    ]
    out = {}
    for k, label in keys_of_interest:
        v = final_state.get(k)
        if v:
            out[label] = _truncate(str(v), 800)
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: analyze_for_bot.py <ticker> [date] [out_json]", file=sys.stderr)
        sys.exit(2)

    ticker = sys.argv[1]
    date = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("/") else (
        dt.date.today() - dt.timedelta(days=1)
    ).strftime("%Y-%m-%d")
    out_path = sys.argv[-1] if sys.argv[-1].endswith(".json") else f"/tmp/ta_{ticker}_{int(time.time())}.json"

    print(f"[analyze] ticker={ticker} date={date} out={out_path}", file=sys.stderr)

    cfg = _config()
    t0 = time.time()
    try:
        ta = TradingAgentsGraph(debug=False, config=cfg)
        final_state, decision = ta.propagate(ticker, date)
        elapsed = time.time() - t0

        result = {
            "ok": True,
            "ticker": ticker,
            "date": date,
            "elapsed_seconds": round(elapsed, 1),
            "decision": decision if isinstance(decision, dict) else {"raw": str(decision)},
            "reports": _extract_reports(final_state),
            "model": cfg["deep_think_llm"],
        }
    except Exception as e:
        elapsed = time.time() - t0
        result = {
            "ok": False,
            "ticker": ticker,
            "date": date,
            "elapsed_seconds": round(elapsed, 1),
            "error": str(e),
            "trace": traceback.format_exc()[-1500:],
        }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # stdout 只输出 JSON 路径，bot 端解析
    print(out_path)
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
