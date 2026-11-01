"""Bounded debate, with explicit evidence and counterarguments."""
def debate(provider, context):
    history = []
    for role in ("bull_researcher", "bear_researcher"):
        response = provider.complete(role, {**context, "debate": history,
            "output_contract": {"thesis": "string", "evidence": ["technical"],
                                "counterarguments": ["string"]}})
        if not isinstance(response.get("thesis"), str) or not response["thesis"].strip():
            raise ValueError(f"{role} needs a thesis")
        history.append({"role": role, "report": response})
    return history
