from plivo import plivoxml

from . import config


def _say(text):
    return plivoxml.SpeakElement(text, voice="Polly.Joanna", language="en-US")


def greeting(first_name=""):
    """Identification first, then options; opt-out offered up front (FCC 47 CFR 64.1200(b))."""
    name = f"Hi {first_name}, " if first_name else "Hi, "
    text = (
        f"{name}this is {config.COMPANY_NAME}, calling because you asked to hear about our offers. "
        "Press 1 to speak with a representative now. "
        "Press 9 to stop receiving calls from us."
    )
    resp = plivoxml.ResponseElement()
    gi = plivoxml.GetInputElement(
        action=f"{config.PUBLIC_URL}/ivr/input",
        method="POST",
        input_type="dtmf",
        num_digits=1,
        digit_end_timeout=5,
        redirect=True,
    )
    gi.add(_say(text))
    resp.add(gi)
    resp.add(_say(
        f"We didn't get a response. To opt out, call {_spell(config.OPT_OUT_PHONE)}. Goodbye."
    ))
    resp.add(plivoxml.HangupElement())
    return resp.to_string()


def connect_agent():
    resp = plivoxml.ResponseElement()
    resp.add(_say("Connecting you to a representative now."))
    dial = plivoxml.DialElement(
        caller_id=config.CALLER_ID,
        timeout=30,
        action=f"{config.PUBLIC_URL}/ivr/dial-status",
        method="POST",
    )
    dial.add(plivoxml.UserElement(config.THREECX_SIP_URI))
    resp.add(dial)
    return resp.to_string()


def opted_out():
    resp = plivoxml.ResponseElement()
    resp.add(_say("You have been removed from our call list. Goodbye."))
    resp.add(plivoxml.HangupElement())
    return resp.to_string()


def invalid_choice():
    resp = plivoxml.ResponseElement()
    resp.add(_say("Sorry, that's not a valid option."))
    resp.add(plivoxml.RedirectElement(f"{config.PUBLIC_URL}/ivr/answer", method="POST"))
    return resp.to_string()


def agents_unavailable():
    resp = plivoxml.ResponseElement()
    resp.add(_say(
        f"All representatives are busy. Call us back at {_spell(config.OPT_OUT_PHONE)}. Goodbye."
    ))
    resp.add(plivoxml.HangupElement())
    return resp.to_string()


def voicemail():
    """Answering machine: identify, give a callback number and the opt-out instruction."""
    resp = plivoxml.ResponseElement()
    resp.add(plivoxml.WaitElement(length=2, beep=True))
    resp.add(_say(
        f"Hi, this is {config.COMPANY_NAME} with an offer you asked to hear about. "
        f"Call us at {_spell(config.OPT_OUT_PHONE)}. "
        f"To stop receiving calls, call the same number and ask to opt out. Thank you."
    ))
    resp.add(plivoxml.HangupElement())
    return resp.to_string()


def _spell(phone):
    return " ".join(phone.lstrip("+1"))
