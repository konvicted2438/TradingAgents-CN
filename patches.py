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


def apply_all():
    _patch_memory()
    _patch_akshare_etf()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    apply_all()
