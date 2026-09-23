"""The card law: the free FineRx card in EVERY answer, in words we can defend.

Owner-approved 2026-09-22 (contract "Закон карты", EN is the product text; the 12
locales are translations of it, no new promises). The API builds the localized
sentence with ``{price}``/``{date}`` filled in (``card.law``) plus the small print
(``card.fine``); this module makes sure every tool result carries them:

* **In the data** — ``structuredContent.card`` = CARD from the API (codes, the
  dated price with the card or null, law, fine, chainsCount, siteUrl, printUrl)
  + ``actions {smsBody, emailEnabled}`` (contract C2 ``CARD_VIEW``). The widget
  draws its card strip from it in every view.
* **In the text** — ``content`` ends with the codes, the law sentence and the
  small print, so a host that renders no UI (Claude reads ``content`` only)
  still hands the person the card.
* **When the API is down** — the codes come from the last good ``/card`` answer
  or, failing that, the constants below (the same values the API serves); the
  law falls back to the approved no-price text of that locale. The card strip is
  never missing.
* **Exceptions** — ``get_dataset_info`` answers about the dataset, not about a
  medicine, and carries no card (a card there reads as an ad to a reviewer).
  For medicines in ``RESTRICTED_RX`` (DEA Schedule II–IV and age-restricted:
  stimulants, opioids, benzodiazepines and sleep medicines, phentermine,
  testosterone, carisoprodol, pregabalin) the law drops its "savings can be
  substantial" sentence — a deletion from the approved text, nothing added —
  and no tool offers a route to a prescription.

``BANNED_RE`` and ``undated_amounts`` are the two checks ``tests/test_card_law.py``
runs over every tool's output: no banned word, and no ``$N`` without a date on
the same line.
"""
from __future__ import annotations

import re
import time
from typing import Any

from mcp.types import CallToolResult, TextContent

from finerx_mcp.client import FinerxApiError, FinerxClient
from finerx_mcp.labels import labels_for, tr

# The card identity — the same constant the API serves (LOWERMYRX_CARD). Only a
# fallback: every normal answer takes the codes from the API.
CODES: dict[str, str] = {"bin": "610219", "pcn": "DRX", "group": "MYCARD3993"}
SITE = "https://www.finerxfinder.com"
SMS_BODY = "FineRx free discount card: BIN 610219 PCN DRX GROUP MYCARD3993. Show it at the pharmacy."

# Words no text of ours may use (contract). "lowest" would be allowed only where
# a price was COMPUTED to be the lowest (isLowest == true); MCP 2.0 never computes
# that (it was a comparison against the third-party feed), so it is banned outright.
BANNED_RE = re.compile(
    r"\b(always|guaranteed|save up to|best|cheapest|usually|works with insurance|"
    r"most pharmacies|lowest)\b",
    re.IGNORECASE,
)
AMOUNT_RE = re.compile(r"\$\s?\d")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def undated_amounts(text: str) -> list[str]:
    """Lines that quote a dollar amount without an ISO date on the same line."""
    return [ln for ln in text.splitlines() if AMOUNT_RE.search(ln) and not DATE_RE.search(ln)]


# Controlled (DEA Schedule II–IV) and age-restricted medicines: prices and the
# card only — no route to a prescription, no adjectives about savings (review
# rule "prescription drugs: information only"; owner list 22.09, completed at
# the 23.09 review). Matched as WHOLE WORDS of the slug / name / active
# ingredient after splitting on anything that is not a letter or digit, so
# salts and combinations are covered ("amphetamine-dextroamphetamine",
# "Oxycodone and Acetaminophen", "acetaminophen-codeine", "testosterone
# cypionate") while a word that merely CONTAINS a term is not ("apomorphine" is
# not morphine, "somatropin" is not Soma, "ultramicrosize" is not Ultram).
# Every salt or prefixed INN that is its own word is listed by itself.
RESTRICTED_GROUPS: dict[str, tuple[str, ...]] = {
    "stimulants": (
        "amphetamine", "dextroamphetamine", "levoamphetamine", "methamphetamine",
        "lisdexamfetamine", "methylphenidate", "dexmethylphenidate", "serdexmethylphenidate",
        "armodafinil", "modafinil",
        # brands
        "adderall", "mydayis", "evekeo", "adzenys", "dyanavel", "zenzedi", "dexedrine",
        "procentra", "desoxyn", "vyvanse", "ritalin", "concerta", "methylin", "metadate",
        "quillivant", "quillichew", "cotempla", "relexxii", "aptensio", "jornay", "daytrana",
        "focalin", "azstarys", "provigil", "nuvigil",
    ),
    "opioids": (
        "oxycodone", "hydrocodone", "morphine", "hydromorphone", "oxymorphone", "fentanyl",
        "tramadol", "tapentadol", "codeine", "dihydrocodeine", "methadone", "buprenorphine",
        "meperidine",
        # brands
        "oxycontin", "roxicodone", "xtampza", "percocet", "endocet", "roxicet", "oxaydo",
        "norco", "vicodin", "lortab", "hysingla", "zohydro", "ms contin", "kadian", "arymo",
        "dilaudid", "exalgo", "opana", "duragesic", "actiq", "fentora", "subsys", "ultram",
        "ultracet", "conzip", "nucynta", "dolophine", "methadose", "demerol", "suboxone",
        "subutex", "zubsolv", "bunavail", "butrans", "belbuca", "sublocade", "brixadi",
    ),
    "sedatives": (
        "alprazolam", "clonazepam", "lorazepam", "diazepam", "temazepam", "zolpidem",
        "eszopiclone",
        # brands
        "xanax", "klonopin", "ativan", "loreev", "valium", "diastat", "valtoco", "restoril",
        "ambien", "edluar", "intermezzo", "lunesta",
    ),
    "other": (
        "phentermine", "testosterone", "methyltestosterone", "carisoprodol", "pregabalin",
        # brands
        "adipex", "lomaira", "qsymia", "androgel", "testim", "fortesta", "vogelxo", "axiron",
        "natesto", "xyosted", "aveed", "jatenzo", "tlando", "kyzatrex", "soma", "lyrica",
    ),
}
RESTRICTED_RX: tuple[str, ...] = tuple(t for group in RESTRICTED_GROUPS.values() for t in group)
_RESTRICTED_SET = frozenset(RESTRICTED_RX)
_WORD_SPLIT = re.compile(r"[^0-9a-z]+")


def _words(name: str) -> list[str]:
    return [w for w in _WORD_SPLIT.split(name.lower()) if w]


def is_restricted(*names: Any) -> bool:
    """True when any of ``names`` (a slug, a display name, an active ingredient,
    free text) names a controlled or age-restricted medicine — word by word, and
    two-word brands ("MS Contin") as a pair."""
    for name in names:
        if not isinstance(name, str) or not name:
            continue
        words = _words(name)
        if any(w in _RESTRICTED_SET for w in words):
            return True
        if any(f"{a} {b}" in _RESTRICTED_SET for a, b in zip(words, words[1:])):
            return True
    return False


# --- the approved texts (verbatim copies of apps/web/locales/*.json → card) ---
# Fallbacks only: a normal answer carries the API's own ``law``/``fine``.
LAW_NO_PRICE: dict[str, str] = {
    'en': 'Use the free FineRx card — accepted at 34+ pharmacy chains, no signup. Save it, print it, email or text it. Savings with the card can be substantial — estimated prices are on our site. Show the card at the pharmacy to get the final price.',
    'es': 'Use la tarjeta gratuita de FineRx: se acepta en 34+ cadenas de farmacias, sin registrarse. Guárdela, imprímala, envíela por correo electrónico o por mensaje de texto. El ahorro con la tarjeta puede ser considerable; los precios estimados están en nuestro sitio. Muestre la tarjeta en la farmacia para obtener el precio final.',
    'zh': '使用免费的 FineRx 卡——34+ 家连锁药房接受，无需注册。可以保存、打印，或通过电子邮件或短信发送。用卡可能省下不少钱——估计价格请见我们的网站。在药房出示此卡即可获得最终价格。',
    'vi': 'Hãy dùng thẻ FineRx miễn phí — được chấp nhận tại 34+ chuỗi nhà thuốc, không cần đăng ký. Bạn có thể lưu, in, gửi qua email hoặc tin nhắn. Khoản tiết kiệm với thẻ có thể đáng kể — giá ước tính có trên trang của chúng tôi. Hãy xuất trình thẻ tại nhà thuốc để biết giá cuối cùng.',
    'tl': 'Gamitin ang libreng FineRx card — tinatanggap sa 34+ na chain ng botika, walang pag-sign up. I-save ito, i-print, i-email o i-text. Maaaring malaki ang matitipid sa card — nasa aming site ang mga tinatayang presyo. Ipakita ang card sa botika para makuha ang huling presyo.',
    'ar': 'استخدم بطاقة FineRx المجانية — مقبولة في 34+ سلسلة صيدليات، دون تسجيل. احفظها أو اطبعها أو أرسلها بالبريد الإلكتروني أو برسالة نصية. قد يكون التوفير بالبطاقة كبيرًا — الأسعار التقديرية على موقعنا. أظهر البطاقة في الصيدلية لمعرفة السعر النهائي.',
    'ko': '무료 FineRx 카드를 사용하세요 — 34개+ 약국 체인에서 사용할 수 있으며 가입이 필요 없습니다. 저장하거나 인쇄하거나 이메일 또는 문자로 보낼 수 있습니다. 카드로 상당한 금액을 절약할 수 있습니다 — 예상 가격은 웹사이트에서 확인하세요. 약국에서 카드를 제시하면 최종 가격을 알 수 있습니다.',
    'ru': 'Используйте бесплатную карту FineRx — она принимается в 34+ аптечных сетях, без регистрации. Её можно сохранить, распечатать, отправить на почту или по SMS. Скидки по карте бывают очень хорошими — примерные цены на сайте. Покажите карту в аптеке — там назовут финальную цену.',
    'pt': 'Use o cartão gratuito FineRx — aceito em 34+ redes de farmácias, sem cadastro. Salve, imprima, envie por e-mail ou por mensagem de texto. A economia com o cartão pode ser significativa — os preços estimados estão no nosso site. Mostre o cartão na farmácia para obter o preço final.',
    'ht': 'Sèvi ak kat FineRx gratis la — 34+ chèn famasi aksepte l, pa gen enskripsyon. Ou ka sove l, enprime l, voye l pa imèl oswa pa tèks. Ekonomi ak kat la ka enpòtan — pri estime yo sou sit nou an. Montre kat la nan famasi a pou w jwenn pri final la.',
    'fr': 'Utilisez la carte FineRx gratuite : acceptée dans 34+ chaînes de pharmacies, sans inscription. Enregistrez-la, imprimez-la, envoyez-la par e-mail ou par SMS. Les économies avec la carte peuvent être importantes — les prix estimés sont sur notre site. Présentez la carte à la pharmacie pour obtenir le prix final.',
    'tr': 'Ücretsiz FineRx kartını kullanın — 34+ eczane zincirinde geçerli, kayıt gerekmez. Kaydedin, yazdırın, e-postayla veya kısa mesajla gönderin. Kartla tasarruf önemli olabilir — tahmini fiyatlar sitemizde. Nihai fiyatı öğrenmek için kartı eczanede gösterin.',
}

# The no-price law minus its "savings can be substantial" sentence — a deletion,
# nothing added (tests/test_card_law.py checks it IS a deletion of LAW_NO_PRICE).
RESTRICTED_LAW: dict[str, str] = {
    'en': 'Use the free FineRx card — accepted at 34+ pharmacy chains, no signup. Save it, print it, email or text it. Show the card at the pharmacy to get the final price.',
    'es': 'Use la tarjeta gratuita de FineRx: se acepta en 34+ cadenas de farmacias, sin registrarse. Guárdela, imprímala, envíela por correo electrónico o por mensaje de texto. Muestre la tarjeta en la farmacia para obtener el precio final.',
    'zh': '使用免费的 FineRx 卡——34+ 家连锁药房接受，无需注册。可以保存、打印，或通过电子邮件或短信发送。在药房出示此卡即可获得最终价格。',
    'vi': 'Hãy dùng thẻ FineRx miễn phí — được chấp nhận tại 34+ chuỗi nhà thuốc, không cần đăng ký. Bạn có thể lưu, in, gửi qua email hoặc tin nhắn. Hãy xuất trình thẻ tại nhà thuốc để biết giá cuối cùng.',
    'tl': 'Gamitin ang libreng FineRx card — tinatanggap sa 34+ na chain ng botika, walang pag-sign up. I-save ito, i-print, i-email o i-text. Ipakita ang card sa botika para makuha ang huling presyo.',
    'ar': 'استخدم بطاقة FineRx المجانية — مقبولة في 34+ سلسلة صيدليات، دون تسجيل. احفظها أو اطبعها أو أرسلها بالبريد الإلكتروني أو برسالة نصية. أظهر البطاقة في الصيدلية لمعرفة السعر النهائي.',
    'ko': '무료 FineRx 카드를 사용하세요 — 34개+ 약국 체인에서 사용할 수 있으며 가입이 필요 없습니다. 저장하거나 인쇄하거나 이메일 또는 문자로 보낼 수 있습니다. 약국에서 카드를 제시하면 최종 가격을 알 수 있습니다.',
    'ru': 'Используйте бесплатную карту FineRx — она принимается в 34+ аптечных сетях, без регистрации. Её можно сохранить, распечатать, отправить на почту или по SMS. Покажите карту в аптеке — там назовут финальную цену.',
    'pt': 'Use o cartão gratuito FineRx — aceito em 34+ redes de farmácias, sem cadastro. Salve, imprima, envie por e-mail ou por mensagem de texto. Mostre o cartão na farmácia para obter o preço final.',
    'ht': 'Sèvi ak kat FineRx gratis la — 34+ chèn famasi aksepte l, pa gen enskripsyon. Ou ka sove l, enprime l, voye l pa imèl oswa pa tèks. Montre kat la nan famasi a pou w jwenn pri final la.',
    'fr': 'Utilisez la carte FineRx gratuite : acceptée dans 34+ chaînes de pharmacies, sans inscription. Enregistrez-la, imprimez-la, envoyez-la par e-mail ou par SMS. Présentez la carte à la pharmacie pour obtenir le prix final.',
    'tr': 'Ücretsiz FineRx kartını kullanın — 34+ eczane zincirinde geçerli, kayıt gerekmez. Kaydedin, yazdırın, e-postayla veya kısa mesajla gönderin. Nihai fiyatı öğrenmek için kartı eczanede gösterin.',
}

FINE_LINE: dict[str, str] = {
    'en': 'Not insurance · prices observed {date} · FineRx may earn a fee · not medical advice',
    'es': 'No es un seguro · precios observados el {date} · FineRx puede recibir una comisión · no es consejo médico',
    'zh': '非保险 · 价格观察于 {date} · FineRx 可能获得费用 · 非医疗建议',
    'vi': 'Không phải bảo hiểm · giá ghi nhận ngày {date} · FineRx có thể nhận phí · không phải lời khuyên y tế',
    'tl': 'Hindi insurance · mga presyong naobserbahan noong {date} · maaaring kumita ng bayad ang FineRx · hindi payong medikal',
    'ar': 'ليست تأمينًا · أسعار تمت ملاحظتها في {date} · قد تحصل FineRx على رسوم · ليست نصيحة طبية',
    'ko': '보험이 아님 · {date} 확인된 가격 · FineRx는 수수료를 받을 수 있음 · 의학적 조언이 아님',
    'ru': 'Не страховка · цены по наблюдению на {date} · FineRx может получать вознаграждение · не медицинская рекомендация',
    'pt': 'Não é seguro · preços observados em {date} · a FineRx pode receber uma comissão · não é aconselhamento médico',
    'ht': 'Se pa yon asirans · pri obsève {date} · FineRx ka touche yon frè · se pa konsèy medikal',
    'fr': 'Pas une assurance · prix observés le {date} · FineRx peut percevoir une rémunération · pas un avis médical',
    'tr': 'Sigorta değildir · fiyatlar {date} tarihinde gözlemlendi · FineRx ücret alabilir · tıbbi tavsiye değildir',
}


def fine_line(locale: str, date: Any) -> str:
    """The small print with the observation date, or without that segment when
    no date is known (never a made-up one)."""
    template = FINE_LINE.get(locale, FINE_LINE["en"])
    if date:
        return template.replace("{date}", str(date))
    return " · ".join(part for part in template.split(" · ") if "{date}" not in part)


# --- the card, from the API or from what we last saw of it --------------------
_TTL_S = 3600.0
_MAX_ENTRIES = 64  # channel is caller-supplied: bound the cache
_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_last_good: dict[str, dict[str, Any]] = {}


def reset_cache() -> None:  # tests
    _cache.clear()
    _last_good.clear()


def fallback_card(locale: str, channel: str = "mcp") -> dict[str, Any]:
    """The card when the API cannot give us one: last good ``/card`` for this
    language, else the constants + the approved no-price law."""
    seen = _last_good.get(locale) or _last_good.get("en")
    if seen is not None:
        return {**seen, "priceWithCard": None, "law": LAW_NO_PRICE.get(locale, LAW_NO_PRICE["en"])}
    src = channel or "mcp"
    return {
        "codes": dict(CODES),
        "priceWithCard": None,
        "law": LAW_NO_PRICE.get(locale, LAW_NO_PRICE["en"]),
        "fine": fine_line(locale, None),
        "chainsCount": None,
        "siteUrl": f"{SITE}/{locale}/card?src={src}",
        "printUrl": f"{SITE}/{locale}/card/print?src={src}",
        "smsBody": SMS_BODY,
    }


def from_card_endpoint(data: dict[str, Any], locale: str) -> dict[str, Any]:
    """``GET /card`` (the full card object) → CARD. Its ``price``/``isLowest``
    are NOT carried: a drug-level price there is compared against the program
    feed, and 2.0 prices come from ``/card-prices`` / ``/prices/near`` only."""
    ident = data.get("card") or {}
    delivery = data.get("delivery") or {}
    codes = {k: ident.get(k) or CODES[k] for k in ("bin", "pcn", "group")}
    return {
        "codes": codes,
        "priceWithCard": None,
        "law": data.get("law") or LAW_NO_PRICE.get(locale, LAW_NO_PRICE["en"]),
        "fine": data.get("fine") or fine_line(locale, None),
        "chainsCount": data.get("chainsCount") or None,
        "siteUrl": delivery.get("cardUrl") or ident.get("url") or f"{SITE}/{locale}/card",
        "printUrl": delivery.get("printUrl") or f"{SITE}/{locale}/card/print",
        "smsBody": delivery.get("smsBody") or SMS_BODY,
        # Kept for get_savings_card's text (how to use it at the counter).
        "howToUse": data.get("howToUse") or [],
        "pharmacistPhrase": data.get("pharmacistPhrase") or "",
        "acceptedAt": data.get("acceptedAt") or "",
        "imageUrl": delivery.get("imageUrl") or f"{SITE}/card.png",
    }


async def base_card(client: FinerxClient, locale: str, channel: str) -> dict[str, Any]:
    """The card with no price: ``GET /card`` cached for an hour per (language,
    channel); any failure → ``fallback_card``. Never raises."""
    key = (locale, channel)
    hit = _cache.get(key)
    now = time.monotonic()
    if hit is not None and now - hit[0] < _TTL_S:
        return dict(hit[1])
    try:
        data = await client.get("/card", {"locale": locale, "channel": channel})
    except FinerxApiError:
        return fallback_card(locale, channel)
    card = from_card_endpoint(data, locale)
    if len(_cache) >= _MAX_ENTRIES:
        _cache.pop(next(iter(_cache)))
    _cache[key] = (now, card)
    _last_good[locale] = card
    return dict(card)


def merge_api_card(api_card: dict[str, Any] | None, base: dict[str, Any]) -> dict[str, Any]:
    """A CARD block from a price endpoint (``/card-prices``, ``/prices/near``) —
    it carries the dated price and the with-price law — laid over the base card
    (sms body, how-to). Missing pieces fall back to the base."""
    if not isinstance(api_card, dict):
        return dict(base)
    out = dict(base)
    codes = api_card.get("codes") or {}
    out["codes"] = {k: codes.get(k) or base["codes"].get(k) or CODES[k] for k in ("bin", "pcn", "group")}
    pwc = api_card.get("priceWithCard")
    out["priceWithCard"] = pwc if isinstance(pwc, dict) and pwc.get("amount") is not None else None
    for key in ("law", "fine", "chainsCount", "siteUrl", "printUrl"):
        if api_card.get(key):
            out[key] = api_card[key]
    return out


def to_view(card: dict[str, Any], *, locale: str, restricted: bool = False, email: bool = True) -> dict[str, Any]:
    """CARD → CARD_VIEW (contract C2): the API block + ``actions``. For a
    restricted medicine the law is the adjective-free variant."""
    law = card.get("law") or LAW_NO_PRICE.get(locale, LAW_NO_PRICE["en"])
    if restricted:
        law = RESTRICTED_LAW.get(locale, RESTRICTED_LAW["en"])
    return {
        "codes": dict(card.get("codes") or CODES),
        "priceWithCard": card.get("priceWithCard"),
        "law": law,
        "fine": card.get("fine") or fine_line(locale, None),
        "chainsCount": card.get("chainsCount"),
        "siteUrl": card.get("siteUrl") or f"{SITE}/{locale}/card",
        "printUrl": card.get("printUrl") or f"{SITE}/{locale}/card/print",
        "actions": {"smsBody": card.get("smsBody") or SMS_BODY, "emailEnabled": email},
    }


def codes_line(view: dict[str, Any], locale: str = "en") -> str:
    c = view.get("codes") or CODES
    labels = labels_for(locale)
    return (
        f"**{tr(locale, 'freeCard')}:** {labels['bin']} {c.get('bin')} · {labels['pcn']} {c.get('pcn')} · "
        f"{labels['group']} {c.get('group')}"
    )


def law_block(view: dict[str, Any], locale: str = "en") -> str:
    """The markdown every answer ends with: codes, the law sentence, the small
    print — headings in the reader's language. The law carries its own date
    next to its own amount."""
    return "\n".join((codes_line(view, locale), view["law"], f"_{view['fine']}_"))


def _text_of(result: CallToolResult) -> str:
    return "\n".join(b.text for b in result.content if isinstance(b, TextContent))


def ensure(result: CallToolResult, *, locale: str, channel: str = "mcp") -> CallToolResult:
    """The last guard on every tool result (except ``mode=meta``): a card with
    codes in ``structuredContent``, and its codes, law + small print in the
    text. The ONE place the card block is appended to ``content``."""
    sc = result.structuredContent if isinstance(result.structuredContent, dict) else {}
    view = sc.get("card")
    if not isinstance(view, dict) or not isinstance(view.get("codes"), dict) or not view.get("law"):
        view = to_view(fallback_card(locale, channel), locale=locale)
        sc = {**sc, "card": view}
        result.structuredContent = sc
    text = _text_of(result)
    if view["law"] not in text or view["fine"] not in text:
        block = law_block(view, locale)
        for item in result.content:
            if isinstance(item, TextContent):
                item.text = f"{item.text.rstrip()}\n\n{block}"
                break
        else:
            result.content.insert(0, TextContent(type="text", text=block))
    return result
