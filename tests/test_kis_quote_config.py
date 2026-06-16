import config


def test_default_kis_quote_base_url_uses_paper_domain_in_paper_mode():
    assert config.TRADE_MODE == "PAPER"
    assert config.KIS.quote_base_url == config.KIS.paper_base_url
