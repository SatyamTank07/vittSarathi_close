INDUSTRY_TEMPLATES = {
    "banking": {
        "quantitative_focus": "Focus on Net Interest Margin (NIM), Non-Performing Assets (NPA/GNPA ratio), Capital Adequacy Ratio (CAR), CASA ratio, Cost-to-Income ratio, and Return on Assets. Credit growth trajectory is critical.",
        "qualitative_focus": "Evaluate branch network reach, digital banking adoption, asset quality management discipline, and regulatory compliance track record.",
        "risk_focus": "Check for rising NPAs, exposure to stressed sectors, asset-liability mismatch, and RBI regulatory actions or penalties.",
    },
    "technology": {
        "quantitative_focus": "Focus on Revenue per Employee, EBITDA margins, order book/deal pipeline, client concentration (top 5 client revenue %), and attrition rate impact on costs.",
        "qualitative_focus": "Evaluate digital transformation capabilities, cloud/AI adoption strategy, client diversification, and ability to move up the value chain from body-shopping to consulting.",
        "risk_focus": "Check for visa regulation risks, currency hedging effectiveness, client concentration risk, and talent retention challenges.",
    },
    "fmcg": {
        "quantitative_focus": "Focus on Volume Growth vs Price Growth decomposition, Gross Margin trends (raw material impact), Distribution reach metrics, and Market Share trajectory.",
        "qualitative_focus": "Evaluate brand power (pricing power test), rural vs urban penetration, new product pipeline, and premiumization strategy.",
        "risk_focus": "Check for commodity price volatility impact, competitive intensity from D2C brands, regulatory risks (FSSAI), and distribution disruption risks.",
    },
    "pharma": {
        "quantitative_focus": "Focus on R&D spend as % of revenue, ANDA pipeline strength, US FDA inspection track record, API vs Formulations revenue mix, and gross margin trends.",
        "qualitative_focus": "Evaluate CRAMS/CDMO opportunity pipeline, biosimilar strategy, domestic market brand strength, and backward integration into APIs.",
        "risk_focus": "Check for FDA warning letters, price erosion in US generics, patent cliffs, and single-facility concentration risk.",
    },
    "default": {
        "quantitative_focus": "Analyze revenue growth trajectory, profit margin expansion/contraction, return ratios (ROE, ROCE), debt levels, and valuation multiples (PE, PB, EV/EBITDA).",
        "qualitative_focus": "Evaluate competitive positioning, management track record, capital allocation discipline, and industry tailwinds/headwinds.",
        "risk_focus": "Check for governance red flags, promoter pledge data, auditor changes, related-party transactions, and cyclical risks.",
    },
}

OrchestratorConfig = {
    "name": "orchestrator",
    "model": "gpt-4o-mini",
    "max_tokens": 700,
    "industry_templates": INDUSTRY_TEMPLATES
}
