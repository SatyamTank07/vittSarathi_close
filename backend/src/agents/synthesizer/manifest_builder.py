from typing import Dict, List, Any
from src.agents.base.shared_state import SharedState, UIManifest, UIComponent, ComponentType, ComponentSize

RATIO_DISPLAY_MAP = {
    # raw_ratios key       label                   size     status_fn
    "NIM_pct":            ("Net Interest Margin",  "small", "nim_status"),
    "Gross_NPA_pct":      ("Gross NPA",            "small", "npa_status"),
    "Net_NPA_pct":        ("Net NPA",              "small", "npa_status"),
    "ROE_pct":            ("Return on Equity",     "small", "roe_status"),
    "ROA_pct":            ("Return on Assets",     "small", "roa_status"),
    "CAR_pct":            ("Capital Adequacy",     "small", "car_status"),
    "PB_Ratio":           ("Price / Book",         "small", "pb_status"),
    "PE_Ratio":           ("Price / Earnings",     "small", "pe_status"),
    "Gross_Margin_pct":   ("Gross Margin",         "small", "margin_status"),
    "EBITDA_Margin_pct":  ("EBITDA Margin",        "small", "margin_status"),
    "Debt_to_Equity":     ("Debt / Equity",        "small", "de_status"),
    "Current_Ratio":      ("Current Ratio",        "small", "cr_status"),
    "ROCE_pct":           ("ROCE",                 "small", "roe_status"),
}

def _nim_status(v):    return "green" if v >= 3.5 else "yellow" if v >= 2.8 else "red"
def _npa_status(v):    return "green" if v <= 1.5 else "yellow" if v <= 3.0 else "red"
def _roe_status(v):    return "green" if v >= 15  else "yellow" if v >= 10  else "red"
def _roa_status(v):    return "green" if v >= 1.5 else "yellow" if v >= 0.8 else "red"
def _car_status(v):    return "green" if v >= 15  else "yellow" if v >= 12  else "red"
def _pb_status(v):     return "green" if v <= 3.0 else "yellow" if v <= 5.0 else "red"
def _pe_status(v):     return "green" if v <= 20  else "yellow" if v <= 35  else "red"
def _margin_status(v): return "green" if v >= 20  else "yellow" if v >= 10  else "red"
def _de_status(v):     return "green" if v <= 0.5 else "yellow" if v <= 1.5 else "red"
def _cr_status(v):     return "green" if v >= 2.0 else "yellow" if v >= 1.0 else "red"

STATUS_FN_MAP = {
    "nim_status": _nim_status,
    "npa_status": _npa_status,
    "roe_status": _roe_status,
    "roa_status": _roa_status,
    "car_status": _car_status,
    "pb_status": _pb_status,
    "pe_status": _pe_status,
    "margin_status": _margin_status,
    "de_status": _de_status,
    "cr_status": _cr_status,
}

SECTION_ORDER = [
    "executive_summary",
    "key_ratios",
    "investment_pillars",
    "risk_dashboard",
    "sentiment",
]

def build_key_ratios_section(state: SharedState) -> List[UIComponent]:
    """
    Returns the list of metric_card components for key_ratios.
    Returns empty list if quantitative data is unavailable.
    """
    components = []
    if state.quantitative_result is not None and state.quantitative_result.status in ["success", "partial"]:
        if state.quantitative and state.quantitative.raw_ratios:
            order_idx = 0
            for key, val in state.quantitative.raw_ratios.items():
                if key in RATIO_DISPLAY_MAP:
                    label, size_str, fn_name = RATIO_DISPLAY_MAP[key]
                    status_fn = STATUS_FN_MAP.get(fn_name)
                    status = None
                    if status_fn is not None and isinstance(val, (int, float)):
                        try:
                            status = status_fn(val)
                        except Exception:
                            pass

                    comp_size = ComponentSize.SMALL
                    if size_str == "medium": comp_size = ComponentSize.MEDIUM
                    elif size_str == "large": comp_size = ComponentSize.LARGE
                    elif size_str == "full": comp_size = ComponentSize.FULL

                    comp_id = "metric_" + key.lower().replace("_pct", "").replace("_ratio", "")
                    
                    components.append(
                        UIComponent(
                            id=comp_id,
                            component_type=ComponentType.METRIC_CARD,
                            size=comp_size,
                            data_path=f"quantitative_result.data.raw_ratios.{key}",
                            label=label,
                            status=status,
                            order=order_idx
                        )
                    )
                    order_idx += 1
    return components

def build_investment_pillars_section(state: SharedState) -> List[UIComponent]:
    """
    Returns the list of pillar_card components for investment_pillars.
    Returns empty list if synthesis.dynamic_investment_pillars is None or empty.
    """
    components = []
    if state.synthesis and state.synthesis.dynamic_investment_pillars:
        order_idx = 0
        for pillar_name, pillar_obj in state.synthesis.dynamic_investment_pillars.items():
            comp_id = "pillar_" + pillar_name.lower().replace(" ", "_")
            
            # derive status
            status = None
            if pillar_obj.supporting_metrics:
                statuses = [m.status.lower() for m in pillar_obj.supporting_metrics if m.status]
                if "red" in statuses:
                    status = "red"
                elif "yellow" in statuses:
                    status = "yellow"
                elif "green" in statuses:
                    status = "green"
                    
            components.append(
                UIComponent(
                    id=comp_id,
                    component_type=ComponentType.PILLAR_CARD,
                    size=ComponentSize.MEDIUM,
                    data_path=f"synthesis.dynamic_investment_pillars.{pillar_name}",
                    label=pillar_name,
                    status=status,
                    order=order_idx
                )
            )
            order_idx += 1
    return components

def build_risk_dashboard_section(state: SharedState) -> List[UIComponent]:
    """
    Returns the list of risk_card components for risk_dashboard.
    Returns empty list if synthesis.key_risk_dashboard is None or empty.
    """
    components = []
    if state.synthesis and state.synthesis.key_risk_dashboard:
        order_idx = 0
        for risk_name, risk_val in state.synthesis.key_risk_dashboard.items():
            comp_id = "risk_" + risk_name.lower().replace(" ", "_").replace("/", "")
            
            status = None
            if risk_val:
                rv = risk_val.strip()
                if rv == "Low": status = "green"
                elif rv in ["Medium", "Elevated"]: status = "yellow"
                elif rv == "High": status = "red"

            components.append(
                UIComponent(
                    id=comp_id,
                    component_type=ComponentType.RISK_CARD,
                    size=ComponentSize.SMALL,
                    data_path=f"synthesis.key_risk_dashboard.{risk_name}",
                    label=risk_name,
                    status=status,
                    order=order_idx
                )
            )
            order_idx += 1
    return components

def build_ui_manifest(state: SharedState) -> UIManifest:
    if state.synthesis is None:
        return UIManifest(layout_sections={})

    layout_sections = {section: [] for section in SECTION_ORDER}

    # Section 1 - executive_summary
    layout_sections["executive_summary"].append(
        UIComponent(
            id="text_executive_summary",
            component_type=ComponentType.TEXT_BLOCK,
            size=ComponentSize.FULL,
            data_path="synthesis.executive_summary",
            label="Executive Summary",
            status=None,
            order=0
        )
    )

    # Sections 2-4 — now delegated
    layout_sections["key_ratios"]          = build_key_ratios_section(state)
    layout_sections["investment_pillars"]  = build_investment_pillars_section(state)
    layout_sections["risk_dashboard"]      = build_risk_dashboard_section(state)

    # Section 5 - sentiment
    if state.sentiment_result is not None and state.sentiment_result.status in ["success", "partial"]:
        if state.sentiment and state.sentiment.market_sentiment:
            status = None
            if state.sentiment.market_sentiment.overall_mood:
                mood = state.sentiment.market_sentiment.overall_mood.strip()
                if mood == "Positive": status = "green"
                elif mood == "Neutral": status = "yellow"
                elif mood == "Negative": status = "red"
                
            layout_sections["sentiment"].append(
                UIComponent(
                    id="sentiment_mood",
                    component_type=ComponentType.SENTIMENT_BLOCK,
                    size=ComponentSize.MEDIUM,
                    data_path="sentiment_result.data.market_sentiment",
                    label="Market Sentiment",
                    status=status,
                    order=0
                )
            )
            
            layout_sections["sentiment"].append(
                UIComponent(
                    id="sentiment_macro",
                    component_type=ComponentType.MACRO_BLOCK,
                    size=ComponentSize.MEDIUM,
                    data_path="sentiment_result.data.macroeconomic_environment",
                    label="Macro Environment",
                    status=None,
                    order=1
                )
            )

    # remove empty sections
    final_layout = {k: v for k, v in layout_sections.items() if len(v) > 0}
    
    return UIManifest(layout_sections=final_layout)
