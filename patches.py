"""
TradingAgents-CN 本地补丁。在 import 框架之前 import 本模块即可。
修三件：
1) MEMORY_ENABLED=false 时直接禁用记忆功能（避免 deepseek 调 embedding 报 401）
2) AKShare 股票信息识别 ETF 代码（5xxxxx / 159xxx 走 ETF 接口）
3) 提供 ETF 名称字典，避免被识别成"股票<code>"
"""
import os
import logging

logger = logging.getLogger(__name__)

# ============ 常见 ETF 名称字典（覆盖 GTAA 策略 + 常用宽基/行业）============
ETF_NAMES = {
    "510300": "沪深300ETF",
    "510500": "中证500ETF",
    "510050": "上证50ETF",
    "159915": "创业板ETF",
    "159928": "消费ETF",
    "159949": "创业板50ETF",
    "159995": "芯片ETF",
    "512000": "券商ETF",
    "512100": "中证1000ETF",
    "512120": "医药ETF",
    "512170": "医疗ETF",
    "512480": "半导体ETF",
    "512660": "军工ETF",
    "512690": "酒ETF",
    "512710": "军工龙头ETF",
    "512760": "芯片ETF",
    "512880": "证券ETF",
    "513050": "中概互联ETF",
    "513100": "纳指ETF",
    "513180": "恒生科技ETF",
    "513500": "标普500ETF",
    "515030": "新能源车ETF",
    "515050": "5G通信ETF",
    "515210": "钢铁ETF",
    "515290": "银行ETF",
    "515700": "新能车ETF",
    "515790": "光伏ETF",
    "515880": "通信ETF",
    "516160": "新能源ETF",
    "518880": "黄金ETF",
    "159980": "有色ETF",
    "511260": "国债ETF",
    "511990": "华宝添益",
    "588000": "科创50ETF",
    "588080": "科创板50ETF",
}


def _is_etf(symbol: str) -> bool:
    """判断是否 ETF 代码。5开头（沪市ETF）或 159开头（深市ETF）。"""
    if len(symbol) != 6:
        return False
    return symbol.startswith(("51", "52", "56", "58", "159"))


# ============ 补丁 1：禁用记忆 ============
def _patch_memory():
    """如果 MEMORY_ENABLED=false，FinancialSituationMemory.__init__ 后强制 client='DISABLED'。"""
    from tradingagents.agents.utils.memory import FinancialSituationMemory

    if os.getenv("MEMORY_ENABLED", "true").lower() == "false":
        original_init = FinancialSituationMemory.__init__

        def patched_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            self.client = "DISABLED"
            logger.info("🚨 [patch] MEMORY_ENABLED=false，记忆功能已禁用")

        FinancialSituationMemory.__init__ = patched_init
        logger.info("✅ [patch] memory 补丁已挂载")


# ============ 补丁 2：AKShare ETF 信息识别 ============
def _patch_akshare_etf():
    """当 symbol 是 ETF 时，跳过 stock_individual_info_em（只接股票），直接返回 ETF 字典。"""
    from tradingagents.dataflows import data_source_manager

    # 找到 AKShare 提供商类
    AKShareProvider = None
    for name in dir(data_source_manager):
        cls = getattr(data_source_manager, name)
        if isinstance(cls, type) and "AKShare" in name and hasattr(cls, "_get_akshare_stock_info"):
            AKShareProvider = cls
            break
        if isinstance(cls, type) and hasattr(cls, "_get_akshare_stock_info"):
            AKShareProvider = cls
            break

    # 直接在 manager 上找
    if AKShareProvider is None and hasattr(data_source_manager, "DataSourceManager"):
        AKShareProvider = data_source_manager.DataSourceManager

    if AKShareProvider is None:
        logger.warning("⚠️ [patch] 找不到含 _get_akshare_stock_info 的类，ETF 补丁跳过")
        return

    original = AKShareProvider._get_akshare_stock_info

    def patched(self, symbol: str):
        if _is_etf(symbol):
            name = ETF_NAMES.get(symbol, f"ETF{symbol}")
            logger.info(f"✅ [patch] ETF 命中: {symbol} -> {name}")
            return {
                "symbol": symbol,
                "name": name,
                "source": "akshare-patch",
                "area": "中国",
                "industry": "ETF基金",
                "market": "上海" if symbol.startswith("5") else "深圳",
                "list_date": "未知",
            }
        return original(self, symbol)

    AKShareProvider._get_akshare_stock_info = patched
    logger.info("✅ [patch] AKShare ETF 补丁已挂载")


# ============ 补丁 3：ETF K 线走 Sina（框架默认 stock_zh_a_hist 不接 ETF）============
def _patch_etf_kline():
    """ETF 代码 → 用 akshare fund_etf_hist_sina 拉数据 → 复用框架格式化器（保留技术指标）"""
    from tradingagents.dataflows import data_source_manager

    DSM = data_source_manager.DataSourceManager
    original_get = DSM.get_stock_data

    def _sina_sym(code):
        return ("sh" if code[0] == "5" else "sz") + code

    def _unwrap(result):
        """框架 _try_fallback_sources 返回 (str, source) 元组但上层未解包；统一兜底。"""
        if isinstance(result, tuple) and len(result) >= 1:
            return result[0]
        return result

    def patched_get_stock_data(self, symbol, start_date=None, end_date=None, period="daily"):
        if not _is_etf(symbol):
            return _unwrap(original_get(self, symbol, start_date, end_date, period))

        import datetime as dt
        import pandas as pd
        import akshare as ak

        try:
            df = ak.fund_etf_hist_sina(symbol=_sina_sym(symbol))
        except Exception as e:
            logger.warning(f"[patch] ETF Sina 拉数失败 {symbol}: {e}")
            return original_get(self, symbol, start_date, end_date, period)

        if df is None or df.empty:
            return original_get(self, symbol, start_date, end_date, period)

        df["date"] = pd.to_datetime(df["date"])
        # 截取范围（默认最近一年）
        if not end_date:
            end_date = dt.date.today().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (dt.datetime.strptime(end_date, "%Y-%m-%d") - dt.timedelta(days=365)).strftime("%Y-%m-%d")
        df = df[(df["date"] >= pd.to_datetime(start_date)) & (df["date"] <= pd.to_datetime(end_date))]
        df = df.sort_values("date").reset_index(drop=True)

        if df.empty:
            return f"❌ ETF {symbol} 在 {start_date} - {end_date} 区间无数据"

        # 周期重采样
        if period == "weekly":
            df = df.set_index("date").resample("W").agg(
                {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}
            ).dropna().reset_index()
        elif period == "monthly":
            df = df.set_index("date").resample("M").agg(
                {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}
            ).dropna().reset_index()

        stock_name = ETF_NAMES.get(symbol, f"ETF{symbol}")
        logger.info(f"✅ [patch] ETF K线 (Sina): {symbol} {stock_name}  {len(df)} 行  {df['date'].iloc[0].date()} → {df['date'].iloc[-1].date()}")

        # 复用框架原有的格式化（含 MA/RSI/MACD/BOLL 等技术指标）
        return self._format_stock_data_response(df, symbol, stock_name, start_date, end_date)

    DSM.get_stock_data = patched_get_stock_data
    logger.info("✅ [patch] ETF K线 (Sina) 补丁已挂载")


def apply_all():
    _patch_memory()
    _patch_akshare_etf()
    _patch_etf_kline()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    apply_all()
