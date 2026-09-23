"""UI strings for the v2 widget, in the 12 site locales — ``_meta["finerx/labels"]``.

The widget (``widget-src/src/labels.ts``) carries the ENGLISH set as a built-in
fallback; the server sends the reader's language with every result, so a
Spanish card never shows an English button. Keys = contract C2 minimum + the
widget-only keys W1 added (``bin`` … ``priceAt``). Placeholders are ``{name}``
and are filled by the widget: ``nearLabel {place}``, ``observed {date}``,
``miles {n}``, ``moreChains {n}``, ``showMore {n}``, ``priceAt {price}
{withCard} {name}``.

The translations are translations of the English — no new promises. The card
law itself is NOT here: it arrives from the API (``card.law``/``card.fine``,
owner-approved text in every locale) and is drawn verbatim. The English set is
held to the card-law word bans by ``tests/test_card_law.py``.
"""
from __future__ import annotations

import functools
import re

EN: dict[str, str] = {
    # --- contract C2 keys ---------------------------------------------------
    "pricesTitle": "Price with the FineRx card, low to high",
    "nearLabel": "Near {place}",
    "approx": "(approximate)",
    "changeZip": "change ZIP",
    "zipPlaceholder": "ZIP code",
    "withCard": "with card",
    "observed": "observed {date}",
    "miles": "{n} mi",
    "moreChains": "+ {n} more chains",
    "allPharmacies": "All pharmacies",
    "showAtCounter": "Show at the counter",
    "save": "Save",
    "print": "Print",
    "email": "Email",
    "sms": "Text message",
    "copy": "Copy",
    "copied": "Copied",
    "noPrice": (
        "We haven't seen a card price for this package yet. Estimated prices are on "
        "our site; show the card at the pharmacy to get the final price."
    ),
    "otherQuantities": "Card prices we have seen for other quantities:",
    "needsZip": "Enter a ZIP code to see pharmacies near you. These are card prices by chain.",
    "notInsurance": "Not insurance",
    "cardTitle": "Prescription Discount Card",
    "cardSub": "Free · no signup · show it to your pharmacist",
    "howToTitle": "At the pharmacy counter",
    "step1": "Show the card, or read out BIN, PCN and Group.",
    "step2": "Ask them to run it as a discount card, not as insurance.",
    "step3": "Ask the price with the card and without it, and pay the lower one.",
    "moreChainOne": "+ 1 more chain",
    "loading": "Loading prices…",
    "error": "Prices didn't load. The card still works.",
    "storeInStore": "pharmacy in store (not verified)",
    "noStock": "We don't see stock — call the pharmacy before you go.",
    # --- widget-only keys ----------------------------------------------------
    "bin": "BIN",
    "pcn": "PCN",
    "group": "Group",
    "zipGo": "OK",
    "zipInvalid": "Enter a 5-digit ZIP code",
    "other": "Other",
    "wallet": "Wallet (printable card)",
    "emailPlaceholder": "Your email",
    "emailSend": "Send card",
    "emailConsent": (
        "We’ll send one email with your card. We don’t store your address and won’t "
        "email you again."
    ),
    "sending": "Sending…",
    "emailSent": "Sent — check your inbox",
    "emailError": "Couldn't send — try again",
    "actionError": "That didn't load. Try again.",
    "directions": "Directions",
    "allFamilies": "All",
    "pharmaciesTitle": "Pharmacies nearby",
    "pricesWithoutStores": "Card price, no store nearby:",
    "showMore": "Show {n} more",
    "close": "Close",
    "noPriceShort": "no card price seen",
    "priceAt": "{price} {withCard} at {name}",
}

_T: dict[str, dict[str, str]] = {
    "es": {
        "pricesTitle": "Precio con la tarjeta FineRx, de menor a mayor",
        "nearLabel": "Cerca de {place}",
        "approx": "(aproximado)",
        "changeZip": "cambiar código postal",
        "zipPlaceholder": "Código postal",
        "withCard": "con tarjeta",
        "observed": "observado el {date}",
        "miles": "{n} mi",
        "moreChains": "+ {n} cadenas más",
        "allPharmacies": "Todas las farmacias",
        "showAtCounter": "Mostrar en el mostrador",
        "save": "Guardar",
        "print": "Imprimir",
        "email": "Correo electrónico",
        "sms": "Mensaje de texto",
        "copy": "Copiar",
        "copied": "Copiado",
        "noPrice": (
            "Aún no hemos visto un precio con tarjeta para este paquete. Los precios "
            "estimados están en nuestro sitio; muestre la tarjeta en la farmacia para "
            "obtener el precio final."
        ),
        "otherQuantities": "Precios con tarjeta que hemos visto para otras cantidades:",
        "needsZip": (
            "Ingrese un código postal para ver farmacias cerca de usted. Estos son "
            "precios con tarjeta por cadena."
        ),
        "notInsurance": "No es un seguro",
        "cardTitle": "Tarjeta de descuento para recetas",
        "cardSub": "Gratis · sin registro · muéstrela en la farmacia",
        "howToTitle": "En el mostrador de la farmacia",
        "step1": "Muestre la tarjeta o dicte BIN, PCN y Group.",
        "step2": "Pida que la procesen como tarjeta de descuento, no como seguro.",
        "step3": "Pregunte el precio con la tarjeta y sin ella, y pague el menor.",
        "moreChainOne": "+ 1 cadena más",
        "loading": "Cargando precios…",
        "error": "Los precios no se cargaron. La tarjeta sigue funcionando.",
        "storeInStore": "farmacia dentro de la tienda (sin verificar)",
        "noStock": "No vemos el inventario: llame a la farmacia antes de ir.",
        "bin": "BIN",
        "pcn": "PCN",
        "group": "Grupo",
        "zipGo": "OK",
        "zipInvalid": "Ingrese un código postal de 5 dígitos",
        "other": "Otra",
        "wallet": "Billetera (tarjeta imprimible)",
        "emailPlaceholder": "Su correo electrónico",
        "emailSend": "Enviar tarjeta",
        "emailConsent": (
            "Le enviaremos un solo correo con su tarjeta. No guardamos su dirección "
            "ni le volveremos a escribir."
        ),
        "sending": "Enviando…",
        "emailSent": "Enviado: revise su bandeja de entrada",
        "emailError": "No se pudo enviar; inténtelo de nuevo",
        "actionError": "No se pudo cargar. Inténtelo de nuevo.",
        "directions": "Cómo llegar",
        "allFamilies": "Todas",
        "pharmaciesTitle": "Farmacias cercanas",
        "pricesWithoutStores": "Precio con tarjeta, sin tienda cercana:",
        "showMore": "Mostrar {n} más",
        "close": "Cerrar",
        "noPriceShort": "sin precio con tarjeta",
        "priceAt": "{price} {withCard} en {name}",
    },
    "zh": {
        "pricesTitle": "使用 FineRx 卡的价格，从低到高",
        "nearLabel": "{place} 附近",
        "approx": "（大致位置）",
        "changeZip": "更改邮编",
        "zipPlaceholder": "邮政编码",
        "withCard": "用卡",
        "observed": "观察于 {date}",
        "miles": "{n} 英里",
        "moreChains": "+ 另外 {n} 家连锁",
        "allPharmacies": "所有药房",
        "showAtCounter": "在柜台出示",
        "save": "保存",
        "print": "打印",
        "email": "电子邮件",
        "sms": "短信",
        "copy": "复制",
        "copied": "已复制",
        "noPrice": "我们尚未见到此包装的用卡价格。估计价格请见我们的网站；在药房出示此卡即可获得最终价格。",
        "otherQuantities": "我们见到的其他数量的用卡价格：",
        "needsZip": "输入邮政编码即可查看附近的药房。以下为各连锁药房的用卡价格。",
        "notInsurance": "非保险",
        "cardTitle": "处方药折扣卡",
        "cardSub": "免费 · 无需注册 · 出示给药剂师",
        "howToTitle": "在药房柜台",
        "step1": "出示卡片，或报出 BIN、PCN 和 Group。",
        "step2": "请药剂师按折扣卡处理，而不是按保险。",
        "step3": "询问用卡和不用卡的价格，支付较低的那个。",
        "moreChainOne": "+ 另外 1 家连锁",
        "loading": "正在加载价格…",
        "error": "价格未能加载。此卡依然可用。",
        "storeInStore": "店内药房（未核实）",
        "noStock": "我们看不到库存——出发前请先致电药房。",
        "bin": "BIN",
        "pcn": "PCN",
        "group": "组号",
        "zipGo": "确定",
        "zipInvalid": "请输入 5 位邮政编码",
        "other": "其他",
        "wallet": "钱包（可打印的卡）",
        "emailPlaceholder": "您的电子邮件",
        "emailSend": "发送卡",
        "emailConsent": "我们只会发送一封附有您的卡的邮件。我们不会保存您的地址，也不会再给您发邮件。",
        "sending": "正在发送…",
        "emailSent": "已发送——请查看收件箱",
        "emailError": "发送失败——请重试",
        "actionError": "未能加载。请重试。",
        "directions": "路线",
        "allFamilies": "全部",
        "pharmaciesTitle": "附近的药房",
        "pricesWithoutStores": "有用卡价格，但附近没有门店：",
        "showMore": "再显示 {n} 个",
        "close": "关闭",
        "noPriceShort": "未见用卡价格",
        "priceAt": "{name}：{price}（{withCard}）",
    },
    "vi": {
        "pricesTitle": "Giá với thẻ FineRx, từ thấp đến cao",
        "nearLabel": "Gần {place}",
        "approx": "(ước tính)",
        "changeZip": "đổi mã ZIP",
        "zipPlaceholder": "Mã ZIP",
        "withCard": "với thẻ",
        "observed": "ghi nhận ngày {date}",
        "miles": "{n} dặm",
        "moreChains": "+ {n} chuỗi khác",
        "allPharmacies": "Tất cả nhà thuốc",
        "showAtCounter": "Xuất trình tại quầy",
        "save": "Lưu",
        "print": "In",
        "email": "Email",
        "sms": "Tin nhắn",
        "copy": "Sao chép",
        "copied": "Đã sao chép",
        "noPrice": (
            "Chúng tôi chưa thấy giá với thẻ cho gói này. Giá ước tính có trên trang "
            "của chúng tôi; hãy xuất trình thẻ tại nhà thuốc để biết giá cuối cùng."
        ),
        "otherQuantities": "Giá với thẻ chúng tôi đã thấy cho số lượng khác:",
        "needsZip": "Nhập mã ZIP để xem các nhà thuốc gần bạn. Đây là giá với thẻ theo chuỗi.",
        "notInsurance": "Không phải bảo hiểm",
        "cardTitle": "Thẻ giảm giá thuốc theo toa",
        "cardSub": "Miễn phí · không cần đăng ký · đưa cho dược sĩ",
        "howToTitle": "Tại quầy nhà thuốc",
        "step1": "Đưa thẻ hoặc đọc mã BIN, PCN và Group.",
        "step2": "Đề nghị xử lý như thẻ giảm giá, không phải bảo hiểm.",
        "step3": "Hỏi giá có thẻ và không có thẻ, rồi trả mức thấp hơn.",
        "moreChainOne": "+ 1 chuỗi nữa",
        "loading": "Đang tải giá…",
        "error": "Không tải được giá. Thẻ vẫn dùng được.",
        "storeInStore": "nhà thuốc trong cửa hàng (chưa xác minh)",
        "noStock": "Chúng tôi không thấy hàng tồn — hãy gọi nhà thuốc trước khi đến.",
        "bin": "BIN",
        "pcn": "PCN",
        "group": "Nhóm",
        "zipGo": "OK",
        "zipInvalid": "Nhập mã ZIP gồm 5 chữ số",
        "other": "Khác",
        "wallet": "Ví (thẻ để in)",
        "emailPlaceholder": "Email của bạn",
        "emailSend": "Gửi thẻ",
        "emailConsent": (
            "Chúng tôi sẽ gửi một email kèm thẻ của bạn. Chúng tôi không lưu địa chỉ "
            "và sẽ không gửi thêm email."
        ),
        "sending": "Đang gửi…",
        "emailSent": "Đã gửi — hãy kiểm tra hộp thư",
        "emailError": "Không gửi được — hãy thử lại",
        "actionError": "Không tải được. Hãy thử lại.",
        "directions": "Chỉ đường",
        "allFamilies": "Tất cả",
        "pharmaciesTitle": "Nhà thuốc gần đây",
        "pricesWithoutStores": "Có giá với thẻ, không có cửa hàng gần:",
        "showMore": "Xem thêm {n}",
        "close": "Đóng",
        "noPriceShort": "chưa thấy giá với thẻ",
        "priceAt": "{price} {withCard} tại {name}",
    },
    "tl": {
        "pricesTitle": "Presyo gamit ang FineRx card, mula mababa hanggang mataas",
        "nearLabel": "Malapit sa {place}",
        "approx": "(tinatayang lokasyon)",
        "changeZip": "palitan ang ZIP",
        "zipPlaceholder": "ZIP code",
        "withCard": "gamit ang card",
        "observed": "naobserbahan noong {date}",
        "miles": "{n} mi",
        "moreChains": "+ {n} pang chain",
        "allPharmacies": "Lahat ng botika",
        "showAtCounter": "Ipakita sa counter",
        "save": "I-save",
        "print": "I-print",
        "email": "Email",
        "sms": "Text message",
        "copy": "Kopyahin",
        "copied": "Nakopya",
        "noPrice": (
            "Wala pa kaming nakitang presyo gamit ang card para sa package na ito. Nasa "
            "aming site ang mga tinatayang presyo; ipakita ang card sa botika para "
            "makuha ang huling presyo."
        ),
        "otherQuantities": "Mga presyo gamit ang card na nakita namin para sa ibang dami:",
        "needsZip": (
            "Maglagay ng ZIP code para makita ang mga botika malapit sa iyo. Ito ang mga "
            "presyo gamit ang card ayon sa chain."
        ),
        "notInsurance": "Hindi insurance",
        "cardTitle": "Discount Card para sa Reseta",
        "cardSub": "Libre · walang pag-sign up · ipakita sa parmasyutiko",
        "howToTitle": "Sa counter ng parmasya",
        "step1": "Ipakita ang card o basahin ang BIN, PCN at Group.",
        "step2": "Hilingin na gamitin ito bilang discount card, hindi insurance.",
        "step3": "Itanong ang presyo na may card at wala, at bayaran ang mas mababa.",
        "moreChainOne": "+ 1 pang chain",
        "loading": "Nilo-load ang mga presyo…",
        "error": "Hindi na-load ang mga presyo. Gumagana pa rin ang card.",
        "storeInStore": "botika sa loob ng tindahan (hindi pa beripikado)",
        "noStock": "Hindi namin nakikita ang stock — tumawag muna sa botika bago pumunta.",
        "bin": "BIN",
        "pcn": "PCN",
        "group": "Group",
        "zipGo": "OK",
        "zipInvalid": "Maglagay ng 5-digit na ZIP code",
        "other": "Iba pa",
        "wallet": "Wallet (card na mapi-print)",
        "emailPlaceholder": "Iyong email",
        "emailSend": "Ipadala ang card",
        "emailConsent": (
            "Magpapadala kami ng isang email na may card mo. Hindi namin itinatago ang "
            "address mo at hindi ka na namin iimeilin ulit."
        ),
        "sending": "Ipinapadala…",
        "emailSent": "Naipadala — tingnan ang inbox mo",
        "emailError": "Hindi naipadala — subukan ulit",
        "actionError": "Hindi na-load. Subukan ulit.",
        "directions": "Direksyon",
        "allFamilies": "Lahat",
        "pharmaciesTitle": "Mga botika sa malapit",
        "pricesWithoutStores": "May presyo gamit ang card, walang tindahan sa malapit:",
        "showMore": "Ipakita ang {n} pa",
        "close": "Isara",
        "noPriceShort": "walang nakitang presyo gamit ang card",
        "priceAt": "{price} {withCard} sa {name}",
    },
    "ar": {
        "pricesTitle": "السعر ببطاقة FineRx، من الأقل إلى الأعلى",
        "nearLabel": "بالقرب من {place}",
        "approx": "(تقريبي)",
        "changeZip": "تغيير الرمز البريدي",
        "zipPlaceholder": "الرمز البريدي",
        "withCard": "بالبطاقة",
        "observed": "تمت ملاحظته في {date}",
        "miles": "{n} ميل",
        "moreChains": "+ {n} سلاسل أخرى",
        "allPharmacies": "كل الصيدليات",
        "showAtCounter": "اعرض البطاقة عند الشباك",
        "save": "حفظ",
        "print": "طباعة",
        "email": "البريد الإلكتروني",
        "sms": "رسالة نصية",
        "copy": "نسخ",
        "copied": "تم النسخ",
        "noPrice": (
            "لم نرَ بعد سعرًا بالبطاقة لهذه العبوة. الأسعار التقديرية على موقعنا؛ أظهر "
            "البطاقة في الصيدلية لمعرفة السعر النهائي."
        ),
        "otherQuantities": "أسعار بالبطاقة رأيناها لكميات أخرى:",
        "needsZip": "أدخل الرمز البريدي لرؤية الصيدليات القريبة منك. هذه أسعار بالبطاقة حسب السلسلة.",
        "notInsurance": "ليست تأمينًا",
        "cardTitle": "بطاقة خصم الوصفات الطبية",
        "cardSub": "مجانية · بدون تسجيل · اعرضها على الصيدلي",
        "howToTitle": "عند شباك الصيدلية",
        "step1": "اعرض البطاقة أو اقرأ BIN وPCN وGroup.",
        "step2": "اطلب معالجتها كبطاقة خصم وليس كتأمين.",
        "step3": "اسأل عن السعر مع البطاقة وبدونها وادفع الأقل.",
        "moreChainOne": "+ سلسلة واحدة أخرى",
        "loading": "جارٍ تحميل الأسعار…",
        "error": "لم يتم تحميل الأسعار. البطاقة ما زالت تعمل.",
        "storeInStore": "صيدلية داخل متجر (لم يتم التحقق)",
        "noStock": "لا نرى المخزون — اتصل بالصيدلية قبل الذهاب.",
        "bin": "BIN",
        "pcn": "PCN",
        "group": "المجموعة",
        "zipGo": "موافق",
        "zipInvalid": "أدخل رمزًا بريديًا من 5 أرقام",
        "other": "أخرى",
        "wallet": "المحفظة (بطاقة للطباعة)",
        "emailPlaceholder": "بريدك الإلكتروني",
        "emailSend": "إرسال البطاقة",
        "emailConsent": "سنرسل رسالة واحدة تحتوي على بطاقتك. لا نحفظ عنوانك ولن نراسلك مرة أخرى.",
        "sending": "جارٍ الإرسال…",
        "emailSent": "تم الإرسال — تحقق من بريدك الوارد",
        "emailError": "تعذّر الإرسال — حاول مرة أخرى",
        "actionError": "لم يتم التحميل. حاول مرة أخرى.",
        "directions": "الاتجاهات",
        "allFamilies": "الكل",
        "pharmaciesTitle": "صيدليات قريبة",
        "pricesWithoutStores": "سعر بالبطاقة، ولا يوجد متجر قريب:",
        "showMore": "عرض {n} أخرى",
        "close": "إغلاق",
        "noPriceShort": "لم نرَ سعرًا بالبطاقة",
        "priceAt": "{price} {withCard} في {name}",
    },
    "ko": {
        "pricesTitle": "FineRx 카드 적용 가격, 낮은 순",
        "nearLabel": "{place} 근처",
        "approx": "(대략적인 위치)",
        "changeZip": "ZIP 변경",
        "zipPlaceholder": "ZIP 코드",
        "withCard": "카드 적용",
        "observed": "{date} 확인",
        "miles": "{n}마일",
        "moreChains": "+ 체인 {n}곳 더",
        "allPharmacies": "모든 약국",
        "showAtCounter": "카운터에서 보여주기",
        "save": "저장",
        "print": "인쇄",
        "email": "이메일",
        "sms": "문자 메시지",
        "copy": "복사",
        "copied": "복사됨",
        "noPrice": (
            "이 포장에 대한 카드 적용 가격을 아직 확인하지 못했습니다. 예상 가격은 웹사이트에서 "
            "확인하세요. 약국에서 카드를 제시하면 최종 가격을 알 수 있습니다."
        ),
        "otherQuantities": "다른 수량에 대해 확인된 카드 적용 가격:",
        "needsZip": "근처 약국을 보려면 ZIP 코드를 입력하세요. 체인별 카드 적용 가격입니다.",
        "notInsurance": "보험이 아님",
        "cardTitle": "처방약 할인 카드",
        "cardSub": "무료 · 가입 불필요 · 약사에게 보여주세요",
        "howToTitle": "약국 카운터에서",
        "step1": "카드를 보여주거나 BIN, PCN, Group을 불러 주세요.",
        "step2": "보험이 아닌 할인 카드로 처리해 달라고 요청하세요.",
        "step3": "카드 사용 시와 미사용 시 가격을 묻고 더 낮은 금액을 내세요.",
        "moreChainOne": "+ 체인 1곳 더",
        "loading": "가격을 불러오는 중…",
        "error": "가격을 불러오지 못했습니다. 카드는 그대로 사용할 수 있습니다.",
        "storeInStore": "매장 내 약국(확인되지 않음)",
        "noStock": "재고는 확인할 수 없습니다 — 방문 전에 약국에 전화하세요.",
        "bin": "BIN",
        "pcn": "PCN",
        "group": "그룹",
        "zipGo": "확인",
        "zipInvalid": "5자리 ZIP 코드를 입력하세요",
        "other": "기타",
        "wallet": "지갑(인쇄용 카드)",
        "emailPlaceholder": "이메일 주소",
        "emailSend": "카드 보내기",
        "emailConsent": "카드가 담긴 이메일을 한 번만 보냅니다. 주소는 저장하지 않으며 다시 이메일을 보내지 않습니다.",
        "sending": "보내는 중…",
        "emailSent": "전송됨 — 받은편지함을 확인하세요",
        "emailError": "보내지 못했습니다 — 다시 시도하세요",
        "actionError": "불러오지 못했습니다. 다시 시도하세요.",
        "directions": "길찾기",
        "allFamilies": "전체",
        "pharmaciesTitle": "근처 약국",
        "pricesWithoutStores": "카드 적용 가격은 있지만 근처 매장이 없음:",
        "showMore": "{n}개 더 보기",
        "close": "닫기",
        "noPriceShort": "카드 적용 가격 없음",
        "priceAt": "{name}: {price} ({withCard})",
    },
    "ru": {
        "pricesTitle": "Цена с картой FineRx, по возрастанию",
        "nearLabel": "Рядом с {place}",
        "approx": "(примерно)",
        "changeZip": "изменить ZIP",
        "zipPlaceholder": "ZIP-код",
        "withCard": "с картой",
        "observed": "по наблюдению на {date}",
        "miles": "{n} миль",
        "moreChains": "+ ещё {n} сетей",
        "allPharmacies": "Все аптеки",
        "showAtCounter": "Показать у кассы",
        "save": "Сохранить",
        "print": "Печать",
        "email": "Эл. почта",
        "sms": "SMS",
        "copy": "Копировать",
        "copied": "Скопировано",
        "noPrice": (
            "Цену по карте для этой упаковки мы ещё не видели. Примерные цены — на "
            "сайте; покажите карту в аптеке — там назовут финальную цену."
        ),
        "otherQuantities": "Цены по карте, которые мы видели для другого количества:",
        "needsZip": "Введите ZIP-код, чтобы увидеть аптеки рядом. Это цены по карте по сетям.",
        "notInsurance": "Не страховка",
        "cardTitle": "Дисконтная карта на рецептурные лекарства",
        "cardSub": "Бесплатно · без регистрации · покажите фармацевту",
        "howToTitle": "У кассы аптеки",
        "step1": "Покажите карту или назовите BIN, PCN и Group.",
        "step2": "Попросите провести её как дисконтную карту, а не как страховку.",
        "step3": "Спросите цену с картой и без неё и заплатите меньшую.",
        "moreChainOne": "+ ещё 1 сеть",
        "loading": "Загружаем цены…",
        "error": "Цены не загрузились. Карта работает и без нас.",
        "storeInStore": "аптека в магазине (не проверено)",
        "noStock": "Наличие мы не видим — позвоните в аптеку перед поездкой.",
        "bin": "BIN",
        "pcn": "PCN",
        "group": "Группа",
        "zipGo": "OK",
        "zipInvalid": "Введите ZIP-код из 5 цифр",
        "other": "Другое",
        "wallet": "Кошелёк (карта для печати)",
        "emailPlaceholder": "Ваш e-mail",
        "emailSend": "Отправить карту",
        "emailConsent": (
            "Мы отправим одно письмо с картой. Мы не храним ваш адрес и больше не "
            "будем вам писать."
        ),
        "sending": "Отправляем…",
        "emailSent": "Отправлено — проверьте почту",
        "emailError": "Не удалось отправить — попробуйте ещё раз",
        "actionError": "Не загрузилось. Попробуйте ещё раз.",
        "directions": "Маршрут",
        "allFamilies": "Все",
        "pharmaciesTitle": "Аптеки рядом",
        "pricesWithoutStores": "Цена по карте, точек рядом нет:",
        "showMore": "Показать ещё {n}",
        "close": "Закрыть",
        "noPriceShort": "цену по карте не видели",
        "priceAt": "{price} {withCard} в {name}",
    },
    "pt": {
        "pricesTitle": "Preço com o cartão FineRx, do menor para o maior",
        "nearLabel": "Perto de {place}",
        "approx": "(aproximado)",
        "changeZip": "alterar código ZIP",
        "zipPlaceholder": "Código ZIP",
        "withCard": "com cartão",
        "observed": "observado em {date}",
        "miles": "{n} mi",
        "moreChains": "+ {n} outras redes",
        "allPharmacies": "Todas as farmácias",
        "showAtCounter": "Mostrar no balcão",
        "save": "Salvar",
        "print": "Imprimir",
        "email": "E-mail",
        "sms": "Mensagem de texto",
        "copy": "Copiar",
        "copied": "Copiado",
        "noPrice": (
            "Ainda não vimos um preço com cartão para esta embalagem. Os preços "
            "estimados estão no nosso site; mostre o cartão na farmácia para obter o "
            "preço final."
        ),
        "otherQuantities": "Preços com cartão que vimos para outras quantidades:",
        "needsZip": (
            "Digite um código ZIP para ver farmácias perto de você. Estes são preços "
            "com cartão por rede."
        ),
        "notInsurance": "Não é seguro",
        "cardTitle": "Cartão de desconto para receitas",
        "cardSub": "Grátis · sem cadastro · mostre ao farmacêutico",
        "howToTitle": "No balcão da farmácia",
        "step1": "Mostre o cartão ou informe BIN, PCN e Group.",
        "step2": "Peça para processar como cartão de desconto, não como seguro.",
        "step3": "Pergunte o preço com o cartão e sem ele, e pague o menor.",
        "moreChainOne": "+ 1 rede",
        "loading": "Carregando preços…",
        "error": "Os preços não carregaram. O cartão continua funcionando.",
        "storeInStore": "farmácia dentro da loja (não verificado)",
        "noStock": "Não vemos o estoque — ligue para a farmácia antes de ir.",
        "bin": "BIN",
        "pcn": "PCN",
        "group": "Grupo",
        "zipGo": "OK",
        "zipInvalid": "Digite um código ZIP de 5 dígitos",
        "other": "Outra",
        "wallet": "Carteira (cartão para imprimir)",
        "emailPlaceholder": "Seu e-mail",
        "emailSend": "Enviar cartão",
        "emailConsent": (
            "Enviaremos um único e-mail com seu cartão. Não guardamos seu endereço e "
            "não enviaremos outros e-mails."
        ),
        "sending": "Enviando…",
        "emailSent": "Enviado — verifique sua caixa de entrada",
        "emailError": "Não foi possível enviar — tente novamente",
        "actionError": "Não carregou. Tente novamente.",
        "directions": "Como chegar",
        "allFamilies": "Todas",
        "pharmaciesTitle": "Farmácias próximas",
        "pricesWithoutStores": "Preço com cartão, sem loja próxima:",
        "showMore": "Mostrar mais {n}",
        "close": "Fechar",
        "noPriceShort": "sem preço com cartão",
        "priceAt": "{price} {withCard} na {name}",
    },
    "ht": {
        "pricesTitle": "Pri ak kat FineRx la, soti nan pi ba rive nan pi wo",
        "nearLabel": "Toupre {place}",
        "approx": "(apeprè)",
        "changeZip": "chanje kòd ZIP",
        "zipPlaceholder": "Kòd ZIP",
        "withCard": "ak kat la",
        "observed": "obsève {date}",
        "miles": "{n} mi",
        "moreChains": "+ {n} lòt chèn",
        "allPharmacies": "Tout famasi yo",
        "showAtCounter": "Montre l nan kontwa a",
        "save": "Sove",
        "print": "Enprime",
        "email": "Imèl",
        "sms": "Mesaj tèks",
        "copy": "Kopye",
        "copied": "Li kopye",
        "noPrice": (
            "Nou poko wè yon pri ak kat la pou pakè sa a. Pri estime yo sou sit nou an; "
            "montre kat la nan famasi a pou w jwenn pri final la."
        ),
        "otherQuantities": "Pri ak kat la nou wè pou lòt kantite:",
        "needsZip": (
            "Antre yon kòd ZIP pou w wè famasi ki toupre w. Sa yo se pri ak kat la "
            "pa chèn."
        ),
        "notInsurance": "Se pa yon asirans",
        "cardTitle": "Kat rabè pou preskripsyon",
        "cardSub": "Gratis · pa bezwen enskri · montre famasyen an li",
        "howToTitle": "Nan kontwa famasi a",
        "step1": "Montre kat la oswa li BIN, PCN ak Group.",
        "step2": "Mande pou yo pase l kòm kat rabè, pa kòm asirans.",
        "step3": "Mande pri a ak kat la ak san li, epi peye pi piti a.",
        "moreChainOne": "+ 1 lòt chèn",
        "loading": "N ap chaje pri yo…",
        "error": "Pri yo pa chaje. Kat la mache kanmenm.",
        "storeInStore": "famasi nan magazen an (pa verifye)",
        "noStock": "Nou pa wè estòk la — rele famasi a anvan w ale.",
        "bin": "BIN",
        "pcn": "PCN",
        "group": "Gwoup",
        "zipGo": "OK",
        "zipInvalid": "Antre yon kòd ZIP 5 chif",
        "other": "Lòt",
        "wallet": "Bous (kat pou enprime)",
        "emailPlaceholder": "Imèl ou",
        "emailSend": "Voye kat la",
        "emailConsent": (
            "N ap voye yon sèl imèl ak kat ou a. Nou pa kenbe adrès ou epi nou p ap "
            "voye w imèl ankò."
        ),
        "sending": "N ap voye…",
        "emailSent": "Li voye — gade bwat resepsyon w",
        "emailError": "Li pa t ka voye — eseye ankò",
        "actionError": "Li pa chaje. Eseye ankò.",
        "directions": "Direksyon",
        "allFamilies": "Tout",
        "pharmaciesTitle": "Famasi ki toupre",
        "pricesWithoutStores": "Pri ak kat la, pa gen magazen toupre:",
        "showMore": "Montre {n} ankò",
        "close": "Fèmen",
        "noPriceShort": "pa wè pri ak kat",
        "priceAt": "{price} {withCard} nan {name}",
    },
    "fr": {
        "pricesTitle": "Prix avec la carte FineRx, par ordre croissant",
        "nearLabel": "Près de {place}",
        "approx": "(approximatif)",
        "changeZip": "modifier le code ZIP",
        "zipPlaceholder": "Code ZIP",
        "withCard": "avec la carte",
        "observed": "observé le {date}",
        "miles": "{n} mi",
        "moreChains": "+ {n} autres chaînes",
        "allPharmacies": "Toutes les pharmacies",
        "showAtCounter": "Montrer au comptoir",
        "save": "Enregistrer",
        "print": "Imprimer",
        "email": "E-mail",
        "sms": "SMS",
        "copy": "Copier",
        "copied": "Copié",
        "noPrice": (
            "Nous n'avons pas encore vu de prix avec la carte pour ce conditionnement. "
            "Les prix estimés sont sur notre site ; présentez la carte à la pharmacie "
            "pour obtenir le prix final."
        ),
        "otherQuantities": "Prix avec la carte observés pour d'autres quantités :",
        "needsZip": (
            "Saisissez un code ZIP pour voir les pharmacies près de chez vous. Ce sont "
            "des prix avec la carte par chaîne."
        ),
        "notInsurance": "Pas une assurance",
        "cardTitle": "Carte de réduction sur ordonnance",
        "cardSub": "Gratuite · sans inscription · montrez-la au pharmacien",
        "howToTitle": "Au comptoir de la pharmacie",
        "step1": "Montrez la carte ou dictez BIN, PCN et Group.",
        "step2": "Demandez de l’utiliser comme carte de réduction, pas comme assurance.",
        "step3": "Demandez le prix avec et sans la carte, et payez le moins élevé.",
        "moreChainOne": "+ 1 chaîne de plus",
        "loading": "Chargement des prix…",
        "error": "Les prix ne se sont pas chargés. La carte fonctionne quand même.",
        "storeInStore": "pharmacie en magasin (non vérifié)",
        "noStock": "Nous ne voyons pas les stocks — appelez la pharmacie avant d'y aller.",
        "bin": "BIN",
        "pcn": "PCN",
        "group": "Groupe",
        "zipGo": "OK",
        "zipInvalid": "Saisissez un code ZIP à 5 chiffres",
        "other": "Autre",
        "wallet": "Portefeuille (carte imprimable)",
        "emailPlaceholder": "Votre e-mail",
        "emailSend": "Envoyer la carte",
        "emailConsent": (
            "Nous enverrons un seul e-mail avec votre carte. Nous ne conservons pas "
            "votre adresse et ne vous écrirons plus."
        ),
        "sending": "Envoi…",
        "emailSent": "Envoyé — consultez votre boîte de réception",
        "emailError": "Échec de l'envoi — réessayez",
        "actionError": "Le chargement a échoué. Réessayez.",
        "directions": "Itinéraire",
        "allFamilies": "Toutes",
        "pharmaciesTitle": "Pharmacies à proximité",
        "pricesWithoutStores": "Prix avec la carte, aucun magasin à proximité :",
        "showMore": "Afficher {n} de plus",
        "close": "Fermer",
        "noPriceShort": "aucun prix avec la carte",
        "priceAt": "{price} {withCard} chez {name}",
    },
    "tr": {
        "pricesTitle": "FineRx kartıyla fiyat, düşükten yükseğe",
        "nearLabel": "{place} yakınında",
        "approx": "(yaklaşık)",
        "changeZip": "ZIP kodunu değiştir",
        "zipPlaceholder": "ZIP kodu",
        "withCard": "kartla",
        "observed": "{date} tarihinde gözlemlendi",
        "miles": "{n} mil",
        "moreChains": "+ {n} zincir daha",
        "allPharmacies": "Tüm eczaneler",
        "showAtCounter": "Kasada göster",
        "save": "Kaydet",
        "print": "Yazdır",
        "email": "E-posta",
        "sms": "Kısa mesaj",
        "copy": "Kopyala",
        "copied": "Kopyalandı",
        "noPrice": (
            "Bu paket için henüz kartla bir fiyat görmedik. Tahmini fiyatlar sitemizde; "
            "nihai fiyatı öğrenmek için kartı eczanede gösterin."
        ),
        "otherQuantities": "Başka miktarlar için gördüğümüz kartla fiyatlar:",
        "needsZip": (
            "Yakınınızdaki eczaneleri görmek için bir ZIP kodu girin. Bunlar zincire "
            "göre kartla fiyatlardır."
        ),
        "notInsurance": "Sigorta değildir",
        "cardTitle": "Reçeteli İlaç İndirim Kartı",
        "cardSub": "Ücretsiz · kayıt gerekmez · eczacıya gösterin",
        "howToTitle": "Eczane tezgâhında",
        "step1": "Kartı gösterin ya da BIN, PCN ve Group kodlarını okuyun.",
        "step2": "Sigorta olarak değil, indirim kartı olarak işlenmesini isteyin.",
        "step3": "Kartlı ve kartsız fiyatı sorun, düşük olanı ödeyin.",
        "moreChainOne": "+ 1 zincir daha",
        "loading": "Fiyatlar yükleniyor…",
        "error": "Fiyatlar yüklenemedi. Kart yine de geçerli.",
        "storeInStore": "mağaza içi eczane (doğrulanmadı)",
        "noStock": "Stok durumunu göremiyoruz — gitmeden önce eczaneyi arayın.",
        "bin": "BIN",
        "pcn": "PCN",
        "group": "Grup",
        "zipGo": "Tamam",
        "zipInvalid": "5 haneli bir ZIP kodu girin",
        "other": "Diğer",
        "wallet": "Cüzdan (yazdırılabilir kart)",
        "emailPlaceholder": "E-posta adresiniz",
        "emailSend": "Kartı gönder",
        "emailConsent": (
            "Kartınızla birlikte tek bir e-posta göndereceğiz. Adresinizi saklamıyoruz "
            "ve size tekrar e-posta göndermeyeceğiz."
        ),
        "sending": "Gönderiliyor…",
        "emailSent": "Gönderildi — gelen kutunuzu kontrol edin",
        "emailError": "Gönderilemedi — tekrar deneyin",
        "actionError": "Yüklenemedi. Tekrar deneyin.",
        "directions": "Yol tarifi",
        "allFamilies": "Tümü",
        "pharmaciesTitle": "Yakındaki eczaneler",
        "pricesWithoutStores": "Kartla fiyat var, yakında mağaza yok:",
        "showMore": "{n} tane daha göster",
        "close": "Kapat",
        "noPriceShort": "kartla fiyat görülmedi",
        "priceAt": "{name}: {price} ({withCard})",
    },
}

LOCALES: tuple[str, ...] = ("en", *_T)


def labels_for(locale: str) -> dict[str, str]:
    """Every key, in ``locale`` where we have it, English otherwise."""
    return {**EN, **_T.get(locale, {})}


# --- the words of ``content``: the markdown the MODEL reads ---------------------
#
# Headings and service phrases of every tool answer (views.py, server.py, the
# card block in card_law.py) in the reader's language — the prices, dates and
# codes are data and never translated. Full sets for en/es/ru; the other nine
# locales borrow the phrases that already exist as widget labels above (stock,
# "with card, observed", miles, pharmacies nearby, the ZIP hint) and read the
# rest in English. Placeholders ``{name}`` are filled by ``tr``; a value is
# never re-scanned for placeholders. Same rules as the widget set: translations
# of the English, no new promises, and the English is held to the card-law word
# bans by ``tests/test_card_law.py``.

TEXT_EN: dict[str, str] = {
    # prices and stores (views.py)
    "withCardObserved": "{price} with the card, observed {date}",
    "zonePrice": "{zone} price",
    "placeZip": "{where} (ZIP {zip})",
    "zipOnly": "ZIP {zip}",
    "placeApprox": "{where} (approximate)",
    "yourArea": "your area",
    "thisMedicine": "this medicine",
    "coverageOther": (
        "We have not seen a card price for {quantity}; card prices were seen for these "
        "quantities: {seen}. A price is never scaled to another quantity."
    ),
    "coverageNone": "We have not seen a card price for this package yet; the pharmacy gives the final price.",
    "pricesNational": (
        "Price with the free FineRx card by pharmacy chain across the US, low to high "
        "(no place given — a ZIP code shows the pharmacies nearby):"
    ),
    "pricesNear": "Price with the free FineRx card near {place}, low to high:",
    "nearestStore": "nearest store {miles} mi",
    "noPriceForPackage": "no card price seen for this package",
    "noPriceShort": "no card price seen",
    "moreChains": "… and {n} more chains in the full list.",
    "noChain": "No pharmacy chain with a card price for this package.",
    "noStoreNearby": "{name} (no store nearby): {price}",
    "perChain": "The card price is set per chain (Walmart: per state), so choose the chain, not the address.",
    "noStock": "We don't see stock — call the pharmacy before you go.",
    "restrictedPrices": "For this medicine FineRx shows card prices and the card only.",
    "pharmaciesNear": "Pharmacies near {place}",
    "pharmaciesNearby": "Pharmacies nearby",
    "noPlace": "No place given: share a 5-digit ZIP code to list the pharmacies nearby.",
    "noStoreInRange": "No store we can place within 30 miles.",
    "storeInStore": "pharmacy in store, not verified",
    "milesShort": "{n} mi",
    "moreNearby": "… and {n} more nearby.",
    "osm": "Store locations © OpenStreetMap contributors (ODbL).",
    "zipInvalid": "A ZIP code must be 5 digits — send a 5-digit ZIP code to see the pharmacies nearby.",
    # answers without data (server.py)
    "rateLimited": "Too many requests right now — try again in {n} s.",
    "loadFailed": "Prices didn't load right now. The card still works.",
    "busy": "Prices are busy right now — try again shortly. The card still works.",
    "drugRequired": "Name the medicine (for example “atorvastatin 20 mg”) to see card prices.",
    "noMatch": "No medicine matched “{query}”. Try search_drugs with another spelling.",
    "closeMatches": "No medicine matched “{query}”. Close matches: {names}.",
    "zipNotFound": "That ZIP code is not one we know. Try a nearby 5-digit ZIP.",
    # the card (get_savings_card, email_savings_card, card_law.law_block)
    "freeCard": "Free FineRx card",
    "cardTitle": "**The free FineRx discount card** — free, no signup, not insurance.",
    "howToUse": "How to use it:",
    "sayAtCounter": "Say at the counter: “{phrase}”",
    "cardLinks": "Card page: {site} · printable sheet: {print}",
    "cardPriceAt": "{package}: {price} with the card at {name}, observed {date}.",
    "noCardPriceFor": "No card price on file for “{drug}”; the card works the same.",
    "emailSent": "Sent the free FineRx card to {to}.",
    # the catalog tools
    "searchHead": "Search “{query}”: {n} match(es).",
    "noCardPriceYet": "no card price seen yet",
    "fromLine": "with the card from {price} for {package}, observed {date}",
    "foreignBrandLine": "Foreign brand {brand} ({countries}): active ingredient {inn} — call find_us_equivalent.",
    "strengthsLine": "Strengths and pack sizes with a card price: {forms}.",
    "noCardPriceAny": "No card price seen for any package of this medicine yet.",
    "cardFromLine": "Card price from {price} for {package}, observed {date}.",
    "defaultPackage": "Default package {label} — card price by chain:",
    "havePrescription": "Have a prescription:",
    "noPrescription": "No prescription yet:",
    "brandCostly": "Brand costs too much:",
    "noOptions": "No options on file.",
    "restrictedRx": (
        "For this medicine FineRx shows only card prices and the free card. "
        "Discuss treatment with a licensed clinician."
    ),
    "usDrugLine": "US drug: {name} (slug {slug}) — {price}.",
    "sameBrandElsewhere": "Same brand name elsewhere: {list}",
    "noForeignMatch": "No foreign brand matched “{brand}”. Try the active ingredient with search_drugs.",
    "brandsAbroad": "Brands abroad that resolve to {slug}: {n}.",
}

_TEXT: dict[str, dict[str, str]] = {
    "es": {
        "withCardObserved": "{price} con la tarjeta, observado el {date}",
        "zonePrice": "precio de {zone}",
        "placeZip": "{where} (código postal {zip})",
        "zipOnly": "código postal {zip}",
        "placeApprox": "{where} (aproximado)",
        "yourArea": "su zona",
        "thisMedicine": "este medicamento",
        "coverageOther": (
            "No hemos visto un precio con tarjeta para {quantity}; se vieron precios con "
            "tarjeta para estas cantidades: {seen}. Un precio nunca se ajusta a otra cantidad."
        ),
        "coverageNone": (
            "Aún no hemos visto un precio con tarjeta para este paquete; la farmacia da el precio final."
        ),
        "pricesNational": (
            "Precio con la tarjeta gratuita FineRx por cadena de farmacias en todo EE. UU., "
            "de menor a mayor (sin lugar indicado: un código postal muestra las farmacias cercanas):"
        ),
        "pricesNear": "Precio con la tarjeta gratuita FineRx cerca de {place}, de menor a mayor:",
        "nearestStore": "tienda más cercana a {miles} mi",
        "noPriceForPackage": "no se ha visto un precio con tarjeta para este paquete",
        "noPriceShort": "no se ha visto un precio con tarjeta",
        "moreChains": "… y {n} cadenas más en la lista completa.",
        "noChain": "Ninguna cadena de farmacias tiene un precio con tarjeta para este paquete.",
        "noStoreNearby": "{name} (sin tienda cercana): {price}",
        "perChain": (
            "El precio con tarjeta lo fija cada cadena (Walmart: por estado), así que elija "
            "la cadena, no la dirección."
        ),
        "noStock": "No vemos el inventario: llame a la farmacia antes de ir.",
        "restrictedPrices": "Para este medicamento, FineRx muestra solo los precios con tarjeta y la tarjeta.",
        "pharmaciesNear": "Farmacias cerca de {place}",
        "pharmaciesNearby": "Farmacias cercanas",
        "noPlace": "Sin lugar indicado: comparta un código postal de 5 dígitos para ver las farmacias cercanas.",
        "noStoreInRange": "No hay ninguna tienda que podamos ubicar a menos de 30 millas.",
        "storeInStore": "farmacia dentro de la tienda, sin verificar",
        "milesShort": "{n} mi",
        "moreNearby": "… y {n} más cerca.",
        "osm": "Ubicación de las tiendas © colaboradores de OpenStreetMap (ODbL).",
        "zipInvalid": (
            "El código postal debe tener 5 dígitos: envíe un código postal de 5 dígitos para "
            "ver las farmacias cercanas."
        ),
        "rateLimited": "Demasiadas solicitudes en este momento: inténtelo de nuevo en {n} s.",
        "loadFailed": "Los precios no se cargaron. La tarjeta sigue funcionando.",
        "busy": "Los precios están ocupados en este momento: inténtelo de nuevo en breve. La tarjeta sigue funcionando.",
        "drugRequired": "Indique el medicamento (por ejemplo, «atorvastatin 20 mg») para ver los precios con tarjeta.",
        "noMatch": "Ningún medicamento coincide con «{query}». Pruebe search_drugs con otra ortografía.",
        "closeMatches": "Ningún medicamento coincide con «{query}». Coincidencias cercanas: {names}.",
        "zipNotFound": "No conocemos ese código postal. Pruebe con un código postal cercano de 5 dígitos.",
        "freeCard": "Tarjeta gratuita FineRx",
        "cardTitle": "**La tarjeta de descuento gratuita FineRx**: gratis, sin registrarse, no es un seguro.",
        "howToUse": "Cómo usarla:",
        "sayAtCounter": "Diga en el mostrador: «{phrase}»",
        "cardLinks": "Página de la tarjeta: {site} · hoja para imprimir: {print}",
        "cardPriceAt": "{package}: {price} con la tarjeta en {name}, observado el {date}.",
        "noCardPriceFor": "No hay un precio con tarjeta registrado para «{drug}»; la tarjeta funciona igual.",
        "emailSent": "Se envió la tarjeta gratuita FineRx a {to}.",
        "searchHead": "Búsqueda «{query}»: {n} resultado(s).",
        "noCardPriceYet": "aún no se ha visto un precio con tarjeta",
        "fromLine": "con la tarjeta desde {price} para {package}, observado el {date}",
        "foreignBrandLine": (
            "Marca extranjera {brand} ({countries}): principio activo {inn}; llame a find_us_equivalent."
        ),
        "strengthsLine": "Dosis y tamaños de envase con precio con tarjeta: {forms}.",
        "noCardPriceAny": "Aún no se ha visto un precio con tarjeta para ningún paquete de este medicamento.",
        "cardFromLine": "Precio con tarjeta desde {price} para {package}, observado el {date}.",
        "defaultPackage": "Paquete predeterminado {label}: precio con tarjeta por cadena:",
        "havePrescription": "Tiene una receta:",
        "noPrescription": "Aún no tiene receta:",
        "brandCostly": "La marca cuesta demasiado:",
        "noOptions": "No hay opciones registradas.",
        "restrictedRx": (
            "Para este medicamento, FineRx muestra solo los precios con tarjeta y la tarjeta gratuita. "
            "Hable del tratamiento con un profesional de salud autorizado."
        ),
        "usDrugLine": "Medicamento en EE. UU.: {name} (slug {slug}): {price}.",
        "sameBrandElsewhere": "La misma marca en otros países: {list}",
        "noForeignMatch": (
            "Ninguna marca extranjera coincide con «{brand}». Pruebe el principio activo con search_drugs."
        ),
        "brandsAbroad": "Marcas en el extranjero que corresponden a {slug}: {n}.",
    },
    "ru": {
        "withCardObserved": "{price} с картой, по наблюдению на {date}",
        "zonePrice": "цена для {zone}",
        "placeZip": "{where} (ZIP {zip})",
        "zipOnly": "ZIP {zip}",
        "placeApprox": "{where} (примерно)",
        "yourArea": "ваш район",
        "thisMedicine": "это лекарство",
        "coverageOther": (
            "Цену с картой для {quantity} мы не видели; цены с картой были для таких количеств: "
            "{seen}. Цена никогда не пересчитывается на другое количество."
        ),
        "coverageNone": "Цену с картой для этой упаковки мы пока не видели; финальную цену назовут в аптеке.",
        "pricesNational": (
            "Цена с бесплатной картой FineRx по аптечным сетям по всем США, по возрастанию "
            "(место не указано — по ZIP-коду покажем аптеки рядом):"
        ),
        "pricesNear": "Цена с бесплатной картой FineRx рядом с {place}, по возрастанию:",
        "nearestStore": "ближайший магазин в {miles} милях",
        "noPriceForPackage": "цену с картой для этой упаковки не видели",
        "noPriceShort": "цену с картой не видели",
        "moreChains": "… и ещё {n} сетей в полном списке.",
        "noChain": "Ни у одной аптечной сети нет цены с картой для этой упаковки.",
        "noStoreNearby": "{name} (рядом нет магазина): {price}",
        "perChain": (
            "Цена с картой задаётся для сети целиком (Walmart — по штату), так что выбирайте сеть, "
            "а не адрес."
        ),
        "noStock": "Наличие мы не видим — позвоните в аптеку перед поездкой.",
        "restrictedPrices": "Для этого лекарства FineRx показывает только цены с картой и саму карту.",
        "pharmaciesNear": "Аптеки рядом с {place}",
        "pharmaciesNearby": "Аптеки рядом",
        "noPlace": "Место не указано: сообщите ZIP-код из 5 цифр, чтобы показать аптеки рядом.",
        "noStoreInRange": "В радиусе 30 миль нет магазинов, которые мы можем показать.",
        "storeInStore": "аптека в магазине, не проверено",
        "milesShort": "{n} миль",
        "moreNearby": "… и ещё {n} рядом.",
        "osm": "Адреса магазинов © участники OpenStreetMap (ODbL).",
        "zipInvalid": "ZIP-код должен состоять из 5 цифр — пришлите ZIP из 5 цифр, чтобы увидеть аптеки рядом.",
        "rateLimited": "Сейчас слишком много запросов — повторите через {n} с.",
        "loadFailed": "Цены сейчас не загрузились. Карта всё равно работает.",
        "busy": "Цены сейчас заняты — повторите чуть позже. Карта всё равно работает.",
        "drugRequired": "Назовите лекарство (например, «atorvastatin 20 mg»), чтобы увидеть цены с картой.",
        "noMatch": "Ни одно лекарство не совпало с «{query}». Попробуйте search_drugs с другим написанием.",
        "closeMatches": "Ни одно лекарство не совпало с «{query}». Похожие: {names}.",
        "zipNotFound": "Такой ZIP-код нам неизвестен. Попробуйте соседний ZIP из 5 цифр.",
        "freeCard": "Бесплатная карта FineRx",
        "cardTitle": "**Бесплатная скидочная карта FineRx** — бесплатно, без регистрации, не страховка.",
        "howToUse": "Как пользоваться:",
        "sayAtCounter": "Скажите у кассы: «{phrase}»",
        "cardLinks": "Страница карты: {site} · лист для печати: {print}",
        "cardPriceAt": "{package}: {price} с картой в {name}, по наблюдению на {date}.",
        "noCardPriceFor": "Цены с картой для «{drug}» у нас нет; карта работает так же.",
        "emailSent": "Бесплатная карта FineRx отправлена на {to}.",
        "searchHead": "Поиск «{query}»: совпадений — {n}.",
        "noCardPriceYet": "цену с картой пока не видели",
        "fromLine": "с картой от {price} за {package}, по наблюдению на {date}",
        "foreignBrandLine": (
            "Зарубежный бренд {brand} ({countries}): действующее вещество {inn} — вызовите find_us_equivalent."
        ),
        "strengthsLine": "Дозировки и упаковки с ценой по карте: {forms}.",
        "noCardPriceAny": "Цену с картой пока не видели ни для одной упаковки этого лекарства.",
        "cardFromLine": "Цена с картой от {price} за {package}, по наблюдению на {date}.",
        "defaultPackage": "Упаковка по умолчанию {label} — цена с картой по сетям:",
        "havePrescription": "Рецепт есть:",
        "noPrescription": "Рецепта пока нет:",
        "brandCostly": "Бренд слишком дорогой:",
        "noOptions": "Вариантов нет.",
        "restrictedRx": (
            "Для этого лекарства FineRx показывает только цены с картой и бесплатную карту. "
            "Лечение обсудите с лицензированным врачом."
        ),
        "usDrugLine": "Лекарство в США: {name} (slug {slug}) — {price}.",
        "sameBrandElsewhere": "Тот же бренд в других странах: {list}",
        "noForeignMatch": (
            "Ни один зарубежный бренд не совпал с «{brand}». Попробуйте действующее вещество через search_drugs."
        ),
        "brandsAbroad": "Зарубежные бренды, соответствующие {slug}: {n}.",
    },
}


def _plain(label: str) -> str:
    """"pharmacy in store (not verified)" → "pharmacy in store, not verified" —
    the content wraps it in parentheses itself."""
    return re.sub(r"\s*[(（]\s*(.*?)\s*[)）]\s*$", r", \1", label)


def _borrowed(locale: str) -> dict[str, str]:
    """Content phrases the widget labels already carry in ``locale``."""
    w = _T.get(locale)
    if not w:
        return {}
    return {
        "withCardObserved": "{price} " + w["withCard"] + ", " + w["observed"],
        "noStock": w["noStock"],
        "storeInStore": _plain(w["storeInStore"]),
        "pharmaciesNearby": w["pharmaciesTitle"],
        "milesShort": w["miles"],
        "noPriceShort": w["noPriceShort"],
        "zipInvalid": w["zipInvalid"] + ".",
    }


@functools.lru_cache(maxsize=16)
def text_for(locale: str) -> dict[str, str]:
    """Every content phrase, in ``locale`` where we have it, English otherwise.
    Treat the answer as read-only (it is cached)."""
    return {**TEXT_EN, **_borrowed(locale), **_TEXT.get(locale, {})}


def tr(locale: str, key: str, **values: object) -> str:
    """One content phrase with its ``{placeholders}`` filled."""
    out = text_for(locale if isinstance(locale, str) else "en")[key]
    for name, value in values.items():
        out = out.replace("{" + name + "}", str(value))
    return out
