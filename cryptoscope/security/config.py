"""Validate settings before starting services. Error messages contain no values."""
import os

TESTNET_URL = 'https://testnet.binance.vision'


def signup_mode(environment=None):
    env = os.environ if environment is None else environment
    mode = (env.get('SIGNUP_MODE') or 'invite').strip().lower()
    if mode not in {'invite', 'invite_only', 'closed', 'open'}:
        raise ValueError('Unsupported signup mode')
    if mode == 'open' and (env.get('ALLOW_OPEN_SIGNUP') or '').lower() not in {'1', 'true'}:
        raise ValueError('Open signup requires an explicit ALLOW_OPEN_SIGNUP override')
    return mode


def validate_testnet_url(url):
    if url.rstrip('/') != TESTNET_URL:
        raise ValueError('Testnet client requires the approved testnet base URL')
    return TESTNET_URL


def validate_startup(mode=None, environment=None):
    env = os.environ if environment is None else environment
    signup_mode(env)
    configured = (env.get('TRADING_MODE') or '').strip().upper()
    requested = mode.upper() if mode else None
    if configured and requested and configured != requested:
        raise ValueError('CLI and configured trading modes disagree')
    selected = requested or configured or 'PAPER'
    if selected not in {'PAPER', 'OBSERVE', 'TESTNET'}:
        raise ValueError('Startup is limited to OBSERVE, PAPER or TESTNET')
    if env.get('EXCHANGE_API_KEY') or env.get('EXCHANGE_API_SECRET'):
        raise ValueError('Ambiguous legacy exchange settings require explicit environment separation')
    if selected == 'TESTNET':
        if env.get('BINANCE_LIVE_API_KEY') or env.get('BINANCE_LIVE_API_SECRET'):
            raise ValueError('Live settings cannot be used in testnet mode')
        if not env.get('BINANCE_TESTNET_API_KEY') or not env.get('BINANCE_TESTNET_API_SECRET'):
            raise ValueError('Testnet configuration is incomplete')
    validate_testnet_url(env.get('BINANCE_TESTNET_BASE_URL') or TESTNET_URL)
    if any(env.get(k) for k in ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_OWNER_CHAT_ID', 'TELEGRAM_OWNER_USER_ID')):
        try:
            chat = int(env.get('TELEGRAM_OWNER_CHAT_ID') or '0')
            user = int(env.get('TELEGRAM_OWNER_USER_ID') or '0')
            if not chat or user <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError('Both Telegram owner settings must be configured') from None
    return selected
