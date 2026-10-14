"""Daily commodity price digest for Telegram.

Uses only the Python standard library. Source pages may change their HTML;
parsing is deliberately fail-closed so missing or stale prices are not sent as
current quotes.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
LOCAL_TZ = timezone(timedelta(hours=7), name="ICT")
TIMEOUT_SECONDS = 20
MAX_HTML_BYTES = 5_000_000
FRESHNESS_DAYS = 3

SOURCES = {
    "gold": "https://sjc.com.vn/",
    "coffee": "https://giacaphe.com/gia-ca-phe-dak-lak",
    "pepper": "https://giacaphe.com/gia-tieu-hom-nay/",
    "durian": "https://giacaphe.com/gia-sau-rieng-hom-nay/",
}


@dataclass
class Quote:
    name: str
    value: str | None
    unit: str
    source: str
    source_date: date | None
    note: str = ""

    @property
    def is_fresh(self) -> bool:
        if self.value is None or self.source_date is None:
            return False
        today = datetime.now(LOCAL_TZ).date()
        return self.source_date >= today - timedelta(days=FRESHNESS_DAYS)


class PageParser(HTMLParser):
    """Extract visible text, headings, and simple HTML tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_parts: list[str] = []
        self.headings: list[str] = []
        self.tables: list[list[list[str]]] = []
        self._tags: list[str] = []
        self._skip_depth = 0
        self._table_depth = 0
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._tags.append(tag)
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._table = []
        elif tag == "tr" and self._table_depth == 1:
            self._row = []
        elif tag in {"td", "th"} and self._table_depth == 1:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._table_depth == 1 and self._cell is not None:
            if self._row is not None:
                self._row.append(clean_text(" ".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._table_depth == 1 and self._row is not None:
            if self._table is not None and self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table":
            if self._table_depth == 1 and self._table is not None:
                if self._table:
                    self.tables.append(self._table)
                self._table = None
            self._table_depth = max(0, self._table_depth - 1)

        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        for index in range(len(self._tags) - 1, -1, -1):
            if self._tags[index] == tag:
                del self._tags[index:]
                break

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        value = clean_text(data)
        if not value:
            return
        self.text_parts.append(value)
        if self._cell is not None:
            self._cell.append(value)
        if any(tag in {"h1", "h2"} for tag in self._tags):
            self.headings.append(value)

    @property
    def visible_text(self) -> str:
        return clean_text(" ".join(self.text_parts))


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def plain_key(value: str) -> str:
    value = unicodedata.normalize("NFD", value.lower().replace("đ", "d"))
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", value).strip()


def parse_number(value: str) -> int | None:
    match = re.search(r"[+-]?\d[\d.,]*", value.replace("−", "-"))
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(0))
    if not digits:
        return None
    number = int(digits)
    return -number if match.group(0).startswith("-") else number


DATE_PATTERN = re.compile(r"(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](20\d{2})(?!\d)")


def parse_date(value: str) -> date | None:
    match = DATE_PATTERN.search(value)
    if not match:
        return None
    try:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None


def page_source_date(page: PageParser) -> date | None:
    for heading in page.headings:
        found = parse_date(heading)
        if found:
            return found
    # Quote dates appear near the beginning on the SJC price page.
    return parse_date(page.visible_text[:1500])


def fetch_page(url: str) -> PageParser:
    request = Request(
        url,
        headers={
            "User-Agent": "PriceWatchTelegram/1.0 (daily public price digest)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = response.read(MAX_HTML_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Không tải được nguồn {url}: {exc}") from exc
    if len(payload) > MAX_HTML_BYTES:
        raise RuntimeError(f"Trang nguồn quá lớn, đã dừng tải: {url}")
    parser = PageParser()
    parser.feed(payload.decode("utf-8", errors="replace"))
    return parser


def table_row_with(rows: list[list[str]], predicate) -> list[str] | None:
    for row in rows:
        if row and predicate(plain_key(" ".join(row))):
            return row
    return None


def parse_gold() -> list[Quote]:
    url = SOURCES["gold"]
    page = fetch_page(url)
    source_date = page_source_date(page)
    candidates: list[list[str]] = []
    for table in page.tables:
        for row in table:
            label = plain_key(row[0]) if row else ""
            if "vang sjc" in label:
                candidates.append(row)

    # Prefer SJC pieces sold as 0.5/1/2 chi when the page exposes that row.
    selected = next(
        (row for row in candidates if "0.5 chi" in plain_key(row[0]) or "0,5 chi" in plain_key(row[0])),
        next((row for row in candidates if row), None),
    )
    if not selected or len(selected) < 3:
        return [Quote("Vàng SJC", None, "đồng/chỉ", url, source_date, "Không đọc được dòng giá mua/bán")]

    buy_thousand_per_luong = parse_number(selected[-2])
    sell_thousand_per_luong = parse_number(selected[-1])
    if buy_thousand_per_luong is None or sell_thousand_per_luong is None:
        return [Quote("Vàng SJC", None, "đồng/chỉ", url, source_date, "Không đọc được giá mua/bán")]

    # SJC labels the table as thousand VND per luong. 1 luong = 10 chi.
    buy_per_chi = buy_thousand_per_luong * 100
    sell_per_chi = sell_thousand_per_luong * 100
    value = f"mua {buy_per_chi:,} / bán {sell_per_chi:,}"
    return [Quote("Vàng SJC", value, "đồng/chỉ", url, source_date)]


def parse_coffee() -> list[Quote]:
    url = SOURCES["coffee"]
    page = fetch_page(url)
    source_date = page_source_date(page)
    dated_rows: list[tuple[date, int, int | None]] = []
    for table in page.tables:
        for row in table:
            if not row:
                continue
            row_date = parse_date(row[0])
            price = parse_number(row[1]) if len(row) > 1 else None
            change = parse_number(row[2]) if len(row) > 2 else None
            if row_date and price:
                dated_rows.append((row_date, price, change))
    if dated_rows:
        row_date, price, change = max(dated_rows, key=lambda item: item[0])
        delta = f" (thay đổi {change:+,})" if change is not None else ""
        return [Quote("Cà phê Đắk Lắk", f"{price:,}{delta}", "đồng/kg", url, row_date)]
    return [Quote("Cà phê Đắk Lắk", None, "đồng/kg", url, source_date, "Không đọc được bảng giá")]


def parse_pepper() -> list[Quote]:
    url = SOURCES["pepper"]
    page = fetch_page(url)
    source_date = page_source_date(page)
    selected: list[str] | None = None
    for table in page.tables:
        selected = table_row_with(table, lambda row: "dak lak" in row)
        if selected:
            break
    price = parse_number(selected[1]) if selected and len(selected) > 1 else None
    if price is None:
        return [Quote("Hồ tiêu Đắk Lắk", None, "đồng/kg", url, source_date, "Không đọc được dòng Đắk Lắk")]
    return [Quote("Hồ tiêu Đắk Lắk", f"{price:,}", "đồng/kg", url, source_date, "Trang Giacaphe ghi nguồn dữ liệu giá là giatieu.com")]


def parse_durian() -> list[Quote]:
    url = SOURCES["durian"]
    page = fetch_page(url)
    source_date = page_source_date(page)
    found: dict[str, tuple[int, int]] = {}
    for table in page.tables:
        for row in table:
            if not row:
                continue
            label = plain_key(row[0])
            if "ri6" in label:
                kind = "Ri6 đẹp" if "dep" in label else "Ri6 xô" if "xo" in label else None
            elif "dona" in label or "monthong" in label:
                kind = "Dona đẹp" if "dep" in label else "Dona xô" if "xo" in label else None
            else:
                kind = None
            numbers = [parse_number(cell) for cell in row[1:]]
            numbers = [number for number in numbers if number is not None]
            if kind and len(numbers) >= 2:
                found[kind] = (numbers[0], numbers[1])

    quotes: list[Quote] = []
    for kind in ("Ri6 đẹp", "Ri6 xô", "Dona đẹp", "Dona xô"):
        prices = found.get(kind)
        value = f"{prices[0]:,}–{prices[1]:,}" if prices else None
        note = ""
        if not prices:
            note = "Không thấy giá cho phân loại này trên trang nguồn"
        quotes.append(Quote(f"Sầu riêng {kind}", value, "đồng/kg", url, source_date, note))
    return quotes


def load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def format_quote(quote: Quote) -> str:
    if quote.source_date is None:
        detail = f" ({quote.note})" if quote.note else ""
        return f"• {quote.name}: chưa lấy được giá mới{detail}.\n  Nguồn: {quote.source}"
    date_text = quote.source_date.strftime("%d/%m/%Y")
    if not quote.is_fresh:
        return f"• {quote.name}: dữ liệu cũ, không dùng làm giá hôm nay (ngày nguồn {date_text}).\n  Nguồn: {quote.source}"
    if quote.value is None:
        return f"• {quote.name}: chưa đọc được giá (ngày nguồn {date_text}).\n  Nguồn: {quote.source}"
    note = f"\n  Ghi chú: {quote.note}" if quote.note else ""
    return f"• {quote.name}: {quote.value} {quote.unit} (ngày nguồn {date_text}).\n  Nguồn: {quote.source}{note}"


def build_report() -> str:
    local_now = datetime.now(LOCAL_TZ)
    quote_groups = []
    parsers = (parse_gold, parse_coffee, parse_pepper, parse_durian)
    for parser in parsers:
        try:
            quote_groups.extend(parser())
        except Exception as exc:  # Keep the daily digest useful when one source fails.
            source_name = parser.__name__.replace("parse_", "").capitalize()
            url = SOURCES.get(source_name.lower(), "")
            quote_groups.append(Quote(source_name, None, "", url, None, f"Lỗi lấy dữ liệu: {exc}"))
    header = f"Giá thị trường — {local_now:%d/%m/%Y %H:%M} (giờ Việt Nam)"
    body = "\n\n".join(format_quote(quote) for quote in quote_groups)
    return f"{header}\n\n{body}"


def telegram_request(method: str, payload: dict | None = None) -> dict:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Thiếu TELEGRAM_BOT_TOKEN trong file .env")
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urlencode(payload or {}).encode("utf-8")
    request = Request(url, data=data, method="POST")
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            import json

            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Telegram API request thất bại: {exc}") from exc
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API từ chối yêu cầu: {result.get('description', 'lỗi không rõ')}")
    return result


def get_chat_id() -> None:
    result = telegram_request("getUpdates")
    chats: dict[str, str] = {}
    for update in result.get("result", []):
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        if chat.get("id") is not None:
            chats[str(chat["id"])] = str(chat.get("type", "chat"))
    if not chats:
        print("Chưa tìm thấy chat. Hãy mở bot trên Telegram, nhấn Start, gửi /start rồi chạy lại lệnh này.")
        return
    print("Chat ID tìm được (chọn ID chat riêng của bạn):")
    for chat_id, chat_type in chats.items():
        print(f"{chat_id} ({chat_type})")
    print("Thêm ID đã chọn vào TELEGRAM_CHAT_ID trong file .env; không cần gửi token cho ai.")


def send_report() -> None:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not chat_id:
        raise RuntimeError("Thiếu TELEGRAM_CHAT_ID trong file .env; chạy lệnh get-chat-id trước.")
    report = build_report()
    telegram_request("sendMessage", {"chat_id": chat_id, "text": report, "disable_web_page_preview": "true"})
    print("Đã gửi báo cáo Telegram.")


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Gửi báo cáo giá hằng ngày qua Telegram")
    parser.add_argument("command", choices=("report", "get-chat-id"), help="report hoặc get-chat-id")
    args = parser.parse_args()
    try:
        if args.command == "get-chat-id":
            get_chat_id()
        else:
            send_report()
    except Exception as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
