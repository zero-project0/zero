# File: billboard_boys_group_complete.py

import csv
import html
import json
import re
import time
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

from bs4 import BeautifulSoup


# ============================================================
# 基本設定
# ============================================================

CHART_CODE = "hot100"
STREAMING_CHART_CODE = "stsongs"
DOWNLOAD_CHART_CODE = "dlsongs"

CHART_CODES = (
    CHART_CODE,
    STREAMING_CHART_CODE,
    DOWNLOAD_CHART_CODE,
)

CHART_NAMES = {
    CHART_CODE: "Billboard Japan Hot 100",
    STREAMING_CHART_CODE: "Billboard Japan Streaming Songs",
    DOWNLOAD_CHART_CODE: "Billboard Japan Download Songs",
}

BASE_URL = "https://www.billboard-japan.com/charts/detail"

# 収集対象は将来の分析に備えて2017年以降を保存します。
# 現在のサイト・比較CSVでは従来どおり2024〜2026年だけを使います。
COLLECTION_YEARS = list(range(2017, 2027))

ANALYSIS_YEARS = (
    2024,
    2025,
    2026,
)

# 完成済みの年は出力CSVを確定データとして再利用します。
# CSVがない場合だけ公式ページから再収集します。
FIXED_YEARS = {
    2017,
    2018,
    2019,
    2020,
    2021,
    2022,
    2023,
    2024,
    2025,
}

PAST_YEAR_WEEKS = {
    2017: 52,
    2018: 52,
    2019: 52,
    2020: 53,
    2021: 52,
    2022: 52,
    2023: 52,
    2024: 52,
    2025: 53,
}

# Streaming SongsとDownload Songsは2017-10-04公開分から開始。
CHART_START_DATES = {
    CHART_CODE: date(2017, 1, 4),
    STREAMING_CHART_CODE: date(2017, 10, 4),
    DOWNLOAD_CHART_CODE: date(2017, 10, 4),
}

EXPECTED_WEEKS_BY_CHART = {
    chart_code: {
        **PAST_YEAR_WEEKS,
        2017: 52 if chart_code == CHART_CODE else 13,
    }
    for chart_code in CHART_CODES
}

MAX_RANK = 100

REQUEST_TIMEOUT_SECONDS = 30
RETRY_COUNT = 3
PAGE_INTERVAL_SECONDS = 0.35

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)

# 正常取得済みのHTMLを再利用します。
USE_CACHE = True

# 2024年または2025年が不完全な場合に、
# 誤った集計サイトを作らず停止します。
REQUIRE_COMPLETE_PAST_YEARS = True

CACHE_DIRECTORY = Path(
    "billboard_cache_wednesday_v3"
)

STREAMING_CACHE_DIRECTORY = Path(
    "billboard_cache_streaming_wednesday_v1"
)

DOWNLOAD_CACHE_DIRECTORY = Path(
    "billboard_cache_download_wednesday_v1"
)

CACHE_DIRECTORIES = {
    CHART_CODE: CACHE_DIRECTORY,
    STREAMING_CHART_CODE: STREAMING_CACHE_DIRECTORY,
    DOWNLOAD_CHART_CODE: DOWNLOAD_CACHE_DIRECTORY,
}

DEBUG_DIRECTORY = Path(
    "billboard_debug_wednesday_v3"
)

OUTPUT_DIRECTORY = Path(
    "billboard_output"
)

COMPARISON_FILE = OUTPUT_DIRECTORY / (
    "boys_group_comparison_2024_2025_2026.csv"
)

MATCH_DETAILS_FILE = OUTPUT_DIRECTORY / (
    "boys_group_matches_2024_2025_2026.csv"
)

COLLECTION_REPORT_FILE = OUTPUT_DIRECTORY / (
    "collection_report_2017_2026.csv"
)

SITE_FILE = OUTPUT_DIRECTORY / (
    "boys_group_power_map_2024_2025_2026.html"
)

PROJECT_DIRECTORY = Path(__file__).resolve().parent
PREVIEW_FILE = PROJECT_DIRECTORY / "preview.html"


# ============================================================
# 集計対象アーティスト
# ============================================================

TARGET_ARTISTS = [
    "BE:FIRST",
    "M!LK",
    "Snow Man",
    "King & Prince",
    "嵐",
    "ONE OR EIGHT",
    "Da-iCE",
    "&TEAM",
    "Number_i",
    "EXILE",
    "NCT WISH",
    "SixTONES",
    "timelesz",
    "Hey! Say! JUMP",
    "NEWS",
    "MAZZEL",
    "なにわ男子",
    "STARGLOW",
    "Travis Japan",
    "三代目 J SOUL BROTHERS from EXILE TRIBE",
    "DA PUMP",
    "NEXZ",
    "GENERATIONS from EXILE TRIBE",
    "SUPER EIGHT",
    "JO1",
    "Kis-My-Ft2",
    "INI",
    "FANTASTICS from EXILE TRIBE",
    "WEST.",
    "THE RAMPAGE from EXILE TRIBE",
    "PSYCHIC FEVER from EXILE TRIBE",
    "DXTEEN",
    "原因は自分にある。",
    "超特急",
    "A.B.C-Z",
    "IMP.",
    "龍宮城",
    "LIL LEAGUE from EXILE TRIBE",
    "KinKi Kids",
    "w-inds.",
    "KID PHENOMENON from EXILE TRIBE",
    "BUDDiiS",
    "THE JET BOY BANGERZ from EXILE TRIBE",
    "BALLISTIK BOYZ from EXILE TRIBE",
    "ONE N' ONLY",
    "WOLF HOWL HARMONY from EXILE TRIBE",
    "Sakurashimeji",
    "SUPER★DRAGON",
    "WILD BLUE",
    "ICEx",
    "Lienel",
    "EXILE THE SECOND",
    "THE SUPER FRUIT",
    "OCTPATH",
    "20th Century",
    "OWV",
    "WATWING",
    "TAGRIGHT",
    "ENJIN",
    "ORβIT",
    "UNiFY",
    "TOKIO",
    "Aぇ! group",
    "7ORDER",
    "aoen",
    "VOKSY DAYS",
    "ROIROM",
    "VIBY",
    "Cloud ten",
    "KO1KEYZ",
    "CLASS SEVEN",
    "iiONDO",
]


ARTIST_ALIASES = {
    artist: [artist]
    for artist in TARGET_ARTISTS
}

# DOMOTO名義をKinKi Kidsとして合算します。
ARTIST_ALIASES["KinKi Kids"] = [
    "KinKi Kids",
    "DOMOTO",
]

GIRLS_GROUP_DATA = json.loads(
    Path(__file__).with_name(
        "girls_group_artists_wikipedia.json"
    ).read_text(encoding="utf-8")
)
GIRLS_GROUP_ARTISTS = GIRLS_GROUP_DATA["artists"]
GIRLS_GROUP_ALIASES = {
    artist: [artist]
    for artist in GIRLS_GROUP_ARTISTS
}
GIRLS_GROUP_ALIASES["モーニング娘。"] = [
    "モーニング娘。",
    "モーニング娘。'24",
    "モーニング娘。'25",
    "モーニング娘。'26",
]

KOREAN_IDOL_DATA = json.loads(
    Path(__file__).with_name(
        "korean_idol_groups_wikipedia.json"
    ).read_text(encoding="utf-8")
)
KOREAN_IDOL_ARTISTS = KOREAN_IDOL_DATA["artists"]
KOREAN_IDOL_ALIASES = {
    artist: KOREAN_IDOL_DATA.get("aliases", {}).get(artist, [artist])
    for artist in KOREAN_IDOL_ARTISTS
}



# ============================================================
# 共通処理
# ============================================================

def normalize_text(value):
    if value is None:
        return ""

    return " ".join(
        str(value)
        .replace("\u3000", " ")
        .replace("\xa0", " ")
        .split()
    ).strip()


def normalize_artist_name(value):
    normalized = unicodedata.normalize(
        "NFKC",
        normalize_text(value),
    )

    normalized = (
        normalized
        .replace("’", "'")
        .replace("‘", "'")
        .replace("＇", "'")
        .replace("“", '"')
        .replace("”", '"')
    )

    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    ).strip()

    return normalized.casefold()


def create_directories():
    for cache_directory in CACHE_DIRECTORIES.values():
        cache_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    DEBUG_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )


def first_wednesday(year):
    first_day = date(
        year,
        1,
        1,
    )

    days_until_wednesday = (
        2 - first_day.weekday()
    ) % 7

    return first_day + timedelta(
        days=days_until_wednesday
    )


def latest_wednesday(reference_date):
    days_since_wednesday = (
        reference_date.weekday() - 2
    ) % 7

    return reference_date - timedelta(
        days=days_since_wednesday
    )


def generate_chart_dates(year, chart_code=CHART_CODE):
    if year > date.today().year:
        return []

    start_date = max(
        first_wednesday(year),
        CHART_START_DATES[chart_code],
    )

    if year == date.today().year:
        end_date = latest_wednesday(
            date.today()
        )
    else:
        end_date = date(
            year,
            12,
            31,
        )

    dates = []
    current = start_date

    while current <= end_date:
        dates.append(current)
        current += timedelta(weeks=1)

    return dates


def build_chart_url(chart_date, chart_code=CHART_CODE):
    # 過去チャートのURLには、公開日の次の月曜日を指定します。
    # 最新公開分は日付なしの現在ページから取得します。
    current_publication_date = latest_wednesday(date.today())
    if chart_date == current_publication_date:
        return f"{BASE_URL}?{urlencode({'a': chart_code})}"

    archive_date = chart_date + timedelta(days=5)
    parameters = {
        "a": chart_code,
        "year": str(archive_date.year),
        "month": f"{archive_date.month:02d}",
        "day": f"{archive_date.day:02d}",
    }
    return f"{BASE_URL}?{urlencode(parameters)}"

def cache_file_path(chart_date, chart_code=CHART_CODE):
    year_directory = (
        CACHE_DIRECTORIES[chart_code]
        / str(chart_date.year)
    )
    year_directory.mkdir(parents=True, exist_ok=True)
    return year_directory / (
        f"{chart_code}_{chart_date.isoformat()}.html"
    )


def debug_html_path(chart_date, chart_code=CHART_CODE):
    return DEBUG_DIRECTORY / (
        f"{chart_code}_{chart_date.isoformat()}.html"
    )

# ============================================================
# ランキングHTML解析
# ============================================================

def parse_chart(html_text):
    soup = BeautifulSoup(
        html_text,
        "html.parser",
    )

    entries = []

    # Download Songsには同順位が複数曲ある週があります。
    # 順位番号を1つずつ探さず、表示されている全行を順番に読み取ります。
    for row in soup.find_all(
        "tr",
        class_=re.compile(r"^rank\d+$"),
    ):
        rank_class = next(
            (
                class_name
                for class_name in row.get("class", [])
                if re.fullmatch(r"rank\d+", class_name)
            ),
            None,
        )

        if rank_class is None:
            continue

        expected_rank = int(rank_class[4:])
        title_element = row.select_one(
            ".musuc_title, .music_title"
        )
        artist_element = row.select_one(
            ".artist_name"
        )

        title = normalize_text(
            title_element.get_text(" ", strip=True)
            if title_element
            else ""
        )
        artist = normalize_text(
            artist_element.get_text(" ", strip=True)
            if artist_element
            else ""
        )

        if not title or not artist:
            continue

        entries.append(
            {
                "rank": expected_rank,
                "title": title,
                "artist": artist,
            }
        )

    return entries


def chart_is_complete(entries):
    if len(entries) < MAX_RANK:
        return False

    actual_ranks = [
        entry["rank"]
        for entry in entries
    ]

    return (
        actual_ranks == sorted(actual_ranks)
        and actual_ranks[0] == 1
        and actual_ranks[-1] <= MAX_RANK
    )


def parse_publication_date(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    date_element = soup.select_one("p.date")
    if date_element is None:
        return None

    match = re.search(
        r"(\d{4})/(\d{2})/(\d{2})",
        date_element.get_text(" ", strip=True),
    )
    if match is None:
        return None

    return date(
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
    )


def chart_html_matches_date(html_text, expected_date):
    return (
        parse_publication_date(html_text) == expected_date
        and chart_is_complete(parse_chart(html_text))
    )


def make_chart_signature(entries):
    return tuple(
        (
            entry["rank"],
            entry["title"],
            entry["artist"],
        )
        for entry in entries
    )


# ============================================================
# HTTP直接取得（ブラウザ不要）
# ============================================================

def create_http_opener():
    return build_opener(HTTPCookieProcessor(CookieJar()))


def save_debug_html(chart_date, html_text, chart_code=CHART_CODE):
    debug_html_path(chart_date, chart_code).write_text(
        html_text,
        encoding="utf-8",
    )


def download_chart_html(opener, url):
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
        },
    )

    with opener.open(
        request,
        timeout=REQUEST_TIMEOUT_SECONDS,
    ) as response:
        raw_html = response.read()
        charset = response.headers.get_content_charset()

    return raw_html.decode(
        charset or "utf-8",
        errors="replace",
    )


def fetch_chart_html(opener, chart_date, chart_code=CHART_CODE):
    cache_file = cache_file_path(chart_date, chart_code)

    if USE_CACHE and cache_file.exists():
        cached_html = cache_file.read_text(
            encoding="utf-8",
            errors="replace",
        )

        if chart_html_matches_date(cached_html, chart_date):
            return cached_html, "キャッシュ"

    # 旧版では公開日の1週間後をファイル名にしていたため、
    # 正しい公開日をHTMLで確認して再利用します。
    legacy_cache_file = cache_file_path(
        chart_date + timedelta(days=7),
        chart_code,
    )
    if USE_CACHE and legacy_cache_file.exists():
        legacy_html = legacy_cache_file.read_text(
            encoding="utf-8",
            errors="replace",
        )
        if chart_html_matches_date(legacy_html, chart_date):
            cache_file.write_text(legacy_html, encoding="utf-8")
            return legacy_html, "キャッシュ移行"

    url = build_chart_url(chart_date, chart_code)
    last_html = ""
    last_error = ""

    for attempt in range(1, RETRY_COUNT + 1):
        try:
            print(
                f"  HTTP接続試行 "
                f"{attempt}/{RETRY_COUNT}"
            )
            html_text = download_chart_html(opener, url)
            entries = parse_chart(html_text)
            publication_date = parse_publication_date(html_text)

            if (
                publication_date == chart_date
                and chart_is_complete(entries)
            ):
                cache_file.write_text(
                    html_text,
                    encoding="utf-8",
                )
                return html_text, "HTTP直接取得"

            last_html = html_text
            if publication_date != chart_date:
                actual_date = (
                    publication_date.isoformat()
                    if publication_date
                    else "不明"
                )
                last_error = (
                    f"公開日が{actual_date}で、"
                    f"期待日{chart_date.isoformat()}と一致しません。"
                )
            else:
                last_error = (
                    f"{len(entries)}件しか"
                    "認識できませんでした。"
                )

        except (HTTPError, URLError, TimeoutError) as error:
            last_error = (
                f"{type(error).__name__}: "
                f"{error}"
            )
        except Exception as error:
            last_error = (
                f"{type(error).__name__}: "
                f"{error}"
            )

        if attempt < RETRY_COUNT:
            time.sleep(2 * attempt)

    if last_html:
        save_debug_html(chart_date, last_html, chart_code)

    print(f"  最終エラー: {last_error}")
    return None, "失敗"

def fixed_year_file(year, chart_code=CHART_CODE):
    return OUTPUT_DIRECTORY / (
        f"billboard_{chart_code}_{year}_entries.csv"
    )


def load_fixed_year(year, chart_code=CHART_CODE):
    input_file = fixed_year_file(year, chart_code)

    if not input_file.exists():
        return None

    entries = []

    with input_file.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        for row in csv.DictReader(file):
            chart_date = date.fromisoformat(
                row["chart_date"]
            )
            entries.append(
                {
                    "chart_year": year,
                    "chart_code": chart_code,
                    "chart_date": chart_date.isoformat(),
                    "rank": int(row["rank"]),
                    "title": row["title"],
                    "artist": row["artist"],
                    "source_url": row["source_url"],
                }
            )

    dates = sorted(
        {
            date.fromisoformat(entry["chart_date"])
            for entry in entries
        }
    )
    expected_weeks = EXPECTED_WEEKS_BY_CHART[chart_code].get(year)
    requested_dates = generate_chart_dates(year, chart_code)
    missing_dates = sorted(set(requested_dates) - set(dates))

    entry_counts_by_date = Counter(
        entry["chart_date"]
        for entry in entries
    )
    entries_are_complete = all(
        entry_counts_by_date[chart_date.isoformat()] >= MAX_RANK
        for chart_date in dates
    )

    if (
        expected_weeks is None
        or (
            len(dates) != expected_weeks
            and year in ANALYSIS_YEARS
        )
        or not entries_are_complete
    ):
        print(
            f"{year}年の確定CSVが不完全なため、"
            "公式ページから再収集します。"
        )
        return None

    print()
    print("=" * 72)
    print(
        f"{year}年は確定CSVを使用します。"
        f"（{len(dates)}週・{len(entries)}件）"
    )
    print("=" * 72)

    reports = [
        {
            "year": year,
            "requested_date": chart_date.isoformat(),
            "status": "確定データ使用",
            "entry_count": MAX_RANK,
            "method": "確定CSV",
            "duplicate_of": "",
        }
        for chart_date in dates
    ]
    reports.extend(
        {
            "year": year,
            "requested_date": chart_date.isoformat(),
            "status": "公式アーカイブ欠損",
            "entry_count": 0,
            "method": "確定CSV",
            "duplicate_of": "",
        }
        for chart_date in missing_dates
    )

    return {
        "year": year,
        "chart_code": chart_code,
        "requested_dates": requested_dates,
        "dates": dates,
        "entries": entries,
        "failed_dates": missing_dates,
        "duplicate_dates": [],
        "reports": reports,
    }

# ============================================================
# 年別データ収集
# ============================================================

def collect_year(
    year,
    opener,
    chart_code=CHART_CODE,
):
    requested_dates = generate_chart_dates(
        year,
        chart_code,
    )

    print()
    print("=" * 72)
    print(f"{CHART_NAMES[chart_code]}・{year}年を取得します。")
    print(f"確認予定: {len(requested_dates)}週")

    if requested_dates:
        print(
            "対象期間: "
            f"{requested_dates[0].isoformat()} ～ "
            f"{requested_dates[-1].isoformat()}"
        )

    print("=" * 72)

    all_entries = []
    successful_dates = []
    failed_dates = []
    duplicate_dates = []
    reports = []

    signatures = {}

    for index, chart_date in enumerate(
        requested_dates,
        start=1,
    ):
        print()
        print(
            f"[{index}/{len(requested_dates)}] "
            f"{chart_date.isoformat()}"
        )

        html_text, method = fetch_chart_html(
            opener,
            chart_date,
            chart_code,
        )

        if html_text is None:
            print("  取得失敗")

            failed_dates.append(
                chart_date
            )

            reports.append(
                {
                    "year": year,
                    "requested_date": (
                        chart_date.isoformat()
                    ),
                    "status": "取得失敗",
                    "entry_count": 0,
                    "method": method,
                    "duplicate_of": "",
                }
            )

            continue

        entries = parse_chart(
            html_text
        )

        if not chart_is_complete(entries):
            print(
                f"  解析失敗: "
                f"{len(entries)}件"
            )

            failed_dates.append(
                chart_date
            )

            reports.append(
                {
                    "year": year,
                    "requested_date": (
                        chart_date.isoformat()
                    ),
                    "status": "解析失敗",
                    "entry_count": len(entries),
                    "method": method,
                    "duplicate_of": "",
                }
            )

            continue

        signature = make_chart_signature(
            entries
        )

        if signature in signatures:
            previous_date = signatures[
                signature
            ]

            print(
                "  重複除外: "
                f"{previous_date.isoformat()}と"
                "同じランキング"
            )

            duplicate_dates.append(
                chart_date
            )

            reports.append(
                {
                    "year": year,
                    "requested_date": (
                        chart_date.isoformat()
                    ),
                    "status": "重複除外",
                    "entry_count": len(entries),
                    "method": method,
                    "duplicate_of": (
                        previous_date.isoformat()
                    ),
                }
            )

            continue

        signatures[
            signature
        ] = chart_date

        successful_dates.append(
            chart_date
        )

        source_url = build_chart_url(
            chart_date,
            chart_code,
        )

        for entry in entries:
            all_entries.append(
                {
                    "chart_year": year,
                    "chart_code": chart_code,
                    "chart_date": (
                        chart_date.isoformat()
                    ),
                    "rank": entry["rank"],
                    "title": entry["title"],
                    "artist": entry["artist"],
                    "source_url": source_url,
                }
            )

        reports.append(
            {
                "year": year,
                "requested_date": (
                    chart_date.isoformat()
                ),
                "status": "取得成功",
                "entry_count": len(entries),
                "method": method,
                "duplicate_of": "",
            }
        )

        print(
            f"  取得成功: "
            f"{len(entries)}件"
            f"（{method}）"
        )

        if method == "HTTP直接取得":
            time.sleep(
                PAGE_INTERVAL_SECONDS
            )

    return {
        "year": year,
        "chart_code": chart_code,
        "requested_dates": requested_dates,
        "dates": successful_dates,
        "entries": all_entries,
        "failed_dates": failed_dates,
        "duplicate_dates": duplicate_dates,
        "reports": reports,
    }


def validate_collection(collection):
    year = collection["year"]
    week_count = len(
        collection["dates"]
    )

    entry_count = len(
        collection["entries"]
    )

    expected_entry_count = (
        week_count * MAX_RANK
    )

    print()
    print("-" * 60)
    print(f"{year}年の収集結果")
    print(f"取得成功: {week_count}週")
    print(f"明細件数: {entry_count}件")
    print(
        f"取得失敗: "
        f"{len(collection['failed_dates'])}週"
    )
    print(
        f"重複除外: "
        f"{len(collection['duplicate_dates'])}週"
    )

    if collection["dates"]:
        print(
            "取得期間: "
            f"{collection['dates'][0].isoformat()} ～ "
            f"{collection['dates'][-1].isoformat()}"
        )

    entry_counts_by_date = Counter(
        entry["chart_date"]
        for entry in collection["entries"]
    )
    entries_are_complete = all(
        entry_counts_by_date[chart_date.isoformat()] >= MAX_RANK
        for chart_date in collection["dates"]
    )

    if not entries_are_complete:
        raise RuntimeError(
            f"{year}年の明細件数が"
            "各週100曲以上の条件を満たしません。"
        )

    required_weeks = EXPECTED_WEEKS_BY_CHART[
        collection["chart_code"]
    ].get(
        year
    )

    if (
        required_weeks is not None
        and week_count != required_weeks
    ):
        message = (
            f"{year}年は{required_weeks}週必要ですが、"
            f"{week_count}週しか取得できませんでした。"
        )

        if REQUIRE_COMPLETE_PAST_YEARS and year in ANALYSIS_YEARS:
            raise RuntimeError(
                message
                + "\n不完全なデータでの集計を防ぐため、"
                "サイト生成を停止します。"
                "\n同じコードを再実行すると、"
                "成功済みの週はキャッシュから読み込まれます。"
            )

        print(f"警告: {message}")
        if year not in ANALYSIS_YEARS:
            print("収集専用年のため、欠損をレポートへ残して処理を続行します。")

    if year == 2025:
        final_date = date(
            2025,
            12,
            31,
        )

        if final_date not in collection["dates"]:
            raise RuntimeError(
                "2025-12-31のランキングを"
                "取得できていません。"
            )


# ============================================================
# CSV出力
# ============================================================

def save_collection_report(collections):
    fieldnames = [
        "chart_code",
        "year",
        "requested_date",
        "status",
        "entry_count",
        "method",
        "duplicate_of",
    ]
    with COLLECTION_REPORT_FILE.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for collection in collections:
            writer.writerows(
                {
                    "chart_code": collection["chart_code"],
                    **report,
                }
                for report in collection["reports"]
            )


def save_year_entries(collection):
    year = collection["year"]
    chart_code = collection["chart_code"]
    output_file = OUTPUT_DIRECTORY / (
        f"billboard_{chart_code}_{year}_entries.csv"
    )
    fieldnames = [
        "chart_year",
        "chart_code",
        "chart_date",
        "rank",
        "title",
        "artist",
        "source_url",
    ]
    with output_file.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(collection["entries"])
    return output_file

# ============================================================
# アーティスト集計
# ============================================================

def build_alias_lookup():
    lookup = {}

    for target_artist, aliases in (
        ARTIST_ALIASES.items()
    ):
        for alias in aliases:
            normalized_alias = (
                normalize_artist_name(alias)
            )

            if normalized_alias in lookup:
                existing_target = lookup[
                    normalized_alias
                ]

                if existing_target != target_artist:
                    raise ValueError(
                        f"名義「{alias}」が"
                        "複数のアーティストに"
                        "登録されています。"
                    )

            lookup[
                normalized_alias
            ] = target_artist

    return lookup


def count_target_artists(
    collection,
    alias_lookup,
):
    counts = Counter()
    alias_counts = Counter()
    matched_entries = []

    for entry in collection["entries"]:
        credited_artist = entry[
            "artist"
        ]

        target_artist = alias_lookup.get(
            normalize_artist_name(
                credited_artist
            )
        )

        if target_artist is None:
            continue

        counts[
            target_artist
        ] += 1

        alias_counts[
            (
                target_artist,
                credited_artist,
            )
        ] += 1

        matched_entries.append(
            {
                "year": collection["year"],
                "target_artist": target_artist,
                "credited_artist": credited_artist,
                "chart_date": entry["chart_date"],
                "rank": entry["rank"],
                "title": entry["title"],
            }
        )

    return (
        counts,
        alias_counts,
        matched_entries,
    )


def calculate_rate(
    previous_count,
    current_count,
):
    if previous_count == 0:
        if current_count == 0:
            return "—"

        return "新規"

    rate = (
        (
            current_count
            - previous_count
        )
        / previous_count
        * 100
    )

    return f"{rate:+.1f}%"


def build_results(counts_by_year):
    original_order = {
        artist: index
        for index, artist in enumerate(
            TARGET_ARTISTS
        )
    }

    results = []

    for artist in TARGET_ARTISTS:
        count_2024 = counts_by_year[
            2024
        ].get(
            artist,
            0,
        )

        count_2025 = counts_by_year[
            2025
        ].get(
            artist,
            0,
        )

        count_2026 = counts_by_year[
            2026
        ].get(
            artist,
            0,
        )

        change_2025 = (
            count_2025 - count_2024
        )

        change_2026 = (
            count_2026 - count_2025
        )

        results.append(
            {
                "artist": artist,
                "count_2024": count_2024,
                "count_2025": count_2025,
                "count_2026": count_2026,
                "change_2025_vs_2024": (
                    change_2025
                ),
                "change_2026_vs_2025": (
                    change_2026
                ),
                "rate_2025_vs_2024": (
                    calculate_rate(
                        count_2024,
                        count_2025,
                    )
                ),
                "rate_2026_vs_2025": (
                    calculate_rate(
                        count_2025,
                        count_2026,
                    )
                ),
                "original_order": (
                    original_order[artist]
                ),
            }
        )

    results.sort(
        key=lambda result: (
            -result["count_2026"],
            -result["count_2025"],
            -result["count_2024"],
            result["original_order"],
        )
    )

    previous_count = None
    current_rank = 0

    for position, result in enumerate(
        results,
        start=1,
    ):
        if (
            result["count_2026"]
            != previous_count
        ):
            current_rank = position

        result["rank_2026"] = (
            current_rank
        )

        previous_count = result[
            "count_2026"
        ]

    return results


def make_alias_summary(
    target_artist,
    alias_counts,
):
    aliases = []

    for (
        counted_target,
        credited_artist,
    ), count in alias_counts.items():
        if counted_target != target_artist:
            continue

        aliases.append(
            (
                credited_artist,
                count,
            )
        )

    aliases.sort(
        key=lambda item: (
            -item[1],
            normalize_artist_name(
                item[0]
            ),
        )
    )

    return " / ".join(
        f"{alias}: {count}回"
        for alias, count in aliases
    )


def save_comparison_csv(
    results,
    collections,
    alias_counts_by_year,
):
    weeks_by_year = {
        collection["year"]: len(
            collection["dates"]
        )
        for collection in collections
    }

    fieldnames = [
        "rank_2026",
        "artist",
        "2024_chart_entries",
        "2025_chart_entries",
        "2026_chart_entries",
        "2025_vs_2024_change",
        "2025_vs_2024_rate",
        "2026_vs_2025_change",
        "2026_vs_2025_rate",
        "2024_matched_credits",
        "2025_matched_credits",
        "2026_matched_credits",
        "2024_weeks",
        "2025_weeks",
        "2026_weeks",
    ]

    with COMPARISON_FILE.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for result in results:
            artist = result["artist"]

            writer.writerow(
                {
                    "rank_2026": (
                        result["rank_2026"]
                    ),
                    "artist": artist,
                    "2024_chart_entries": (
                        result["count_2024"]
                    ),
                    "2025_chart_entries": (
                        result["count_2025"]
                    ),
                    "2026_chart_entries": (
                        result["count_2026"]
                    ),
                    "2025_vs_2024_change": (
                        result[
                            "change_2025_vs_2024"
                        ]
                    ),
                    "2025_vs_2024_rate": (
                        result[
                            "rate_2025_vs_2024"
                        ]
                    ),
                    "2026_vs_2025_change": (
                        result[
                            "change_2026_vs_2025"
                        ]
                    ),
                    "2026_vs_2025_rate": (
                        result[
                            "rate_2026_vs_2025"
                        ]
                    ),
                    "2024_matched_credits": (
                        make_alias_summary(
                            artist,
                            alias_counts_by_year[2024],
                        )
                    ),
                    "2025_matched_credits": (
                        make_alias_summary(
                            artist,
                            alias_counts_by_year[2025],
                        )
                    ),
                    "2026_matched_credits": (
                        make_alias_summary(
                            artist,
                            alias_counts_by_year[2026],
                        )
                    ),
                    "2024_weeks": (
                        weeks_by_year[2024]
                    ),
                    "2025_weeks": (
                        weeks_by_year[2025]
                    ),
                    "2026_weeks": (
                        weeks_by_year[2026]
                    ),
                }
            )


def save_match_details(matched_entries):
    artist_order = {
        artist: index
        for index, artist in enumerate(
            TARGET_ARTISTS
        )
    }

    def rank_number(entry):
        try:
            return int(entry["rank"])
        except (TypeError, ValueError):
            return 999

    matched_entries.sort(
        key=lambda entry: (
            entry["year"],
            artist_order[
                entry["target_artist"]
            ],
            entry["chart_date"],
            rank_number(entry),
        )
    )

    fieldnames = [
        "year",
        "target_artist",
        "credited_artist",
        "chart_date",
        "rank",
        "title",
    ]

    with MATCH_DETAILS_FILE.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(
            matched_entries
        )


# ============================================================
# サイト作成
# ============================================================

def period_text(dates):
    if not dates:
        return "データなし"

    return (
        f"{dates[0].isoformat()}"
        f"〜{dates[-1].isoformat()}"
    )


def build_dashboard_data(matched_entries, collections, chart_code, artist_names=None):
    collections_by_year = {
        collection["year"]: collection
        for collection in collections
    }
    dates_by_year = {
        year: sorted(collections_by_year[year]["dates"])
        for year in ANALYSIS_YEARS
    }
    current_dates = dates_by_year[2026]
    latest_date = current_dates[-1]
    comparison_dates = set(
        dates_by_year[2025][:len(current_dates)]
    )
    if artist_names is None:
        artist_names = sorted(
            {
                entry["target_artist"]
                for entry in matched_entries
            }
        )

    entries_by_artist = {
        artist: []
        for artist in artist_names
    }
    for entry in matched_entries:
        item = dict(entry)
        item["chart_date"] = date.fromisoformat(
            str(entry["chart_date"])
        )
        item["rank"] = int(entry["rank"])
        if item["target_artist"] in entries_by_artist:
            entries_by_artist[item["target_artist"]].append(item)

    artists = []
    global_songs = {}

    for artist in artist_names:
        entries = entries_by_artist[artist]
        by_year = {
            year: [item for item in entries if item["year"] == year]
            for year in ANALYSIS_YEARS
        }
        current = by_year[2026]
        previous_ytd = [
            item for item in by_year[2025]
            if item["chart_date"] in comparison_dates
        ]
        current_weeks = {
            item["chart_date"] for item in current
        }

        weekly_cumulative = {}
        for comparison_year in ANALYSIS_YEARS:
            counts_by_date = Counter(
                item["chart_date"]
                for item in by_year[comparison_year]
            )
            running_total = 0
            cumulative_values = []
            for weekly_date in dates_by_year[comparison_year]:
                running_total += counts_by_date[weekly_date]
                cumulative_values.append(running_total)
            weekly_cumulative[str(comparison_year)] = cumulative_values

        song_groups = {}
        for item in current:
            song = song_groups.setdefault(
                item["title"],
                {"title": item["title"], "entries": []},
            )
            song["entries"].append(item)

            global_key = (artist, item["title"])
            global_song = global_songs.setdefault(
                global_key,
                {"artist": artist, "title": item["title"], "entries": []},
            )
            global_song["entries"].append(item)

        songs = []
        for song in song_groups.values():
            song_entries = song["entries"]
            songs.append(
                {
                    "title": song["title"],
                    "appearances": len(song_entries),
                    "weeks": len({item["chart_date"] for item in song_entries}),
                    "best": min(item["rank"] for item in song_entries),
                    "latest": max(item["chart_date"] for item in song_entries).isoformat(),
                    "history": [
                        {
                            "date": item["chart_date"].isoformat(),
                            "rank": item["rank"],
                        }
                        for item in sorted(song_entries, key=lambda value: value["chart_date"])
                    ],
                }
            )
        songs.sort(key=lambda item: (-item["appearances"], item["best"], item["title"]))

        appearances = len(current)
        artist_data = {
            "artist": artist,
            "appearances": appearances,
            "weeks": len(current_weeks),
            "songsCount": len(song_groups),
            "top10": sum(item["rank"] <= 10 for item in current),
            "best": min((item["rank"] for item in current), default=None),
            "active": any(item["chart_date"] == latest_date for item in current),
            "previousYtd": len(previous_ytd),
            "ytdChange": appearances - len(previous_ytd),
            "weeklyCumulative": weekly_cumulative,
            "yearCounts": {
                str(year): len(by_year[year])
                for year in ANALYSIS_YEARS
            },
            "songs": songs,
        }
        artists.append(artist_data)

    artists.sort(
        key=lambda item: (
            -item["appearances"],
            -item["top10"],
            -item["weeks"],
            item["artist"],
        )
    )
    for index, item in enumerate(artists, start=1):
        item["rank"] = index
    artist_details = artists
    artists = artists[:50]

    songs = []
    for song in global_songs.values():
        entries = song["entries"]
        latest_entries = [
            item for item in entries
            if item["chart_date"] == latest_date
        ]
        songs.append(
            {
                "artist": song["artist"],
                "title": song["title"],
                "appearances": len(entries),
                "weeks": len({item["chart_date"] for item in entries}),
                "best": min(item["rank"] for item in entries),
                "top10": sum(item["rank"] <= 10 for item in entries),
                "latestRank": min(
                    (item["rank"] for item in latest_entries),
                    default=None,
                ),
            }
        )
    songs.sort(
        key=lambda item: (
            -item["appearances"],
            item["best"],
            item["artist"],
        )
    )
    latest_songs = sorted(
        (
            song for song in songs
            if song["latestRank"] is not None
        ),
        key=lambda item: (
            item["latestRank"],
            item["artist"],
            item["title"],
        ),
    )

    return {
        "chartName": CHART_NAMES[chart_code],
        "artists": artists,
        "artistDetails": artist_details,
        "songs": songs[:30],
        "latestSongs": latest_songs,
        "latestDate": latest_date.isoformat(),
        "weeks2026": len(current_dates),
        "comparisonWeeks": len(comparison_dates),
        "periods": {
            str(year): period_text(dates_by_year[year])
            for year in ANALYSIS_YEARS
        },
    }

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>JAPAN CHART PULSE</title>
<style>
:root{--paper:#f4f4f0;--white:#fff;--ink:#050505;--muted:#686868;--line:#0a0a0a;--soft:#deded8;--acid:#b8ff25;--cyan:#25d8ff;--pink:#ff4b91;--violet:#7557ff;--green:#15935a;--red:#d62f49;--shadow:0 12px 30px rgba(0,0,0,.08)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;color:var(--ink);background:var(--paper);font-family:Arial,"Hiragino Kaku Gothic ProN","Yu Gothic UI",sans-serif;line-height:1.55}button,input,select{font:inherit}button{cursor:pointer;color:inherit}.wrap{width:min(1220px,calc(100% - 40px));margin:auto}
.top{position:sticky;top:0;z-index:30;background:#050505;color:#fff;border-bottom:1px solid #333}.topin{display:flex;align-items:center;justify-content:space-between;min-height:64px;gap:20px}.brand{display:flex;align-items:center;gap:11px;color:#fff;font-size:.82rem;font-weight:1000;letter-spacing:.16em;text-decoration:none}.mark{display:grid;width:38px;height:38px;place-items:center;background:var(--acid);color:#050505;font-weight:1000}nav{display:flex;gap:3px}nav a{padding:8px 11px;color:#fff;font-size:.72rem;font-weight:900;text-decoration:none;text-transform:uppercase}nav a:hover{background:var(--acid);color:#050505}
.hero{padding:68px 0 54px;background:#050505;color:#fff;border-bottom:10px solid var(--acid)}.eyebrow{display:inline-block;margin:0 0 20px;padding:5px 9px;background:var(--acid);color:#050505;font-size:.7rem;font-weight:1000;letter-spacing:.14em}h1{max-width:1000px;margin:0;font-family:Arial Black,Arial,sans-serif;font-size:clamp(3.4rem,8.5vw,7.2rem);font-weight:1000;letter-spacing:-.085em;line-height:.84}.slash{color:var(--acid)}.lead{max-width:720px;margin:24px 0 0;color:#d7d7d7;font-size:clamp(.96rem,1.5vw,1.15rem);font-weight:700}.scope-tabs{display:inline-flex;gap:0;margin-top:26px;border:1px solid #666}.scope-tab{padding:9px 14px;border:0;border-right:1px solid #666;background:#050505;color:#fff;font-size:.68rem;font-weight:1000;letter-spacing:.08em}.scope-tab:last-child{border-right:0}.scope-tab:hover{background:#272727}.scope-tab.active{background:#fff;color:#050505}.chart-tabs{display:inline-flex;flex-wrap:wrap;gap:4px;margin-top:26px;padding:4px;border:1px solid #555;background:#171717}.chart-tab{padding:10px 17px;border:0;background:transparent;color:#fff;font-size:.78rem;font-weight:1000}.chart-tab:hover{background:#292929}.chart-tab.active{background:var(--acid);color:#050505}.fresh{display:flex;flex-wrap:wrap;gap:7px;margin-top:17px}.pill{padding:6px 10px;border:1px solid #4b4b4b;background:#111;color:#e5e5e5;font-size:.7rem;font-weight:800}
.section{padding:48px 0}.section:nth-of-type(even){background:#fff}.section-head{display:flex;align-items:end;justify-content:space-between;gap:24px;margin-bottom:22px;padding-top:13px;border-top:5px solid var(--line)}.kicker{margin:0 0 5px;color:#577b00;font-size:.68rem;font-weight:1000;letter-spacing:.18em;text-transform:uppercase}.section h2{margin:0;font-family:Arial Black,Arial,sans-serif;font-size:clamp(1.9rem,4vw,3.4rem);letter-spacing:-.06em;line-height:.95}.section-copy{max-width:510px;margin:0;color:var(--muted);font-size:.82rem;font-weight:600}
.latest-section{padding-top:34px;background:#fff}.latest-section .section-head{border-top-color:var(--acid)}.latest-grid{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid var(--line);border-left:1px solid var(--line)}.latest-song{display:grid;grid-template-columns:50px 1fr;gap:12px;align-items:center;min-height:112px;padding:15px;border:0;border-right:1px solid var(--line);border-bottom:1px solid var(--line);background:#fff;text-align:left;transition:.14s}.latest-song:hover{background:var(--acid)}.latest-rank{font-family:Arial Black,Arial,sans-serif;font-size:1.25rem;font-weight:1000;letter-spacing:-.05em}.latest-title{display:block;font-size:.91rem;font-weight:1000;line-height:1.25}.latest-artist{display:block;margin-top:5px;color:var(--muted);font-size:.68rem;font-weight:900}.latest-song:hover .latest-artist{color:#222}
.stats{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid var(--line);border-left:1px solid var(--line)}.stat{min-height:145px;padding:19px;border-right:1px solid var(--line);border-bottom:1px solid var(--line);background:#fff}.stat:first-child{background:var(--acid)}.stat-label{color:var(--muted);font-size:.7rem;font-weight:900}.stat:first-child .stat-label{color:#273300}.stat-value{margin-top:9px;font-family:Arial Black,Arial,sans-serif;font-size:clamp(1.6rem,3.5vw,2.45rem);font-weight:1000;letter-spacing:-.06em;line-height:1}.stat-note{margin-top:8px;color:var(--muted);font-size:.7rem;font-weight:700}
.card-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.artist-card{position:relative;min-height:238px;padding:17px;border:1px solid var(--line);border-radius:0;background:#fff;text-align:left;box-shadow:none;transition:.14s}.artist-card:hover{transform:translateY(-4px);box-shadow:8px 8px 0 var(--acid)}.card-rank{font-size:.68rem;font-weight:1000;color:var(--muted)}.artist-card h3{margin:15px 0 20px;font-size:1.15rem;line-height:1.13}.big-number{font-family:Arial Black,Arial,sans-serif;font-size:2.45rem;font-weight:1000;letter-spacing:-.07em}.mini-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:13px}.mini{border-top:1px solid var(--soft);padding-top:6px;font-size:.64rem;color:var(--muted)}.mini strong{display:block;color:var(--ink);font-size:.9rem}.live{position:absolute;right:10px;top:10px;padding:3px 6px;background:var(--acid);font-size:.57rem;font-weight:1000}
.panel{padding:0;border:1px solid var(--line);background:#fff;box-shadow:none}.tools{display:flex;flex-wrap:wrap;gap:8px;padding:14px;border-bottom:1px solid var(--line);background:#f7f7f3}.tools input,.tools select,.compare-add select{min-height:42px;padding:8px 11px;border:1px solid var(--line);border-radius:0;background:#fff}.tools input{flex:1;min-width:220px}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;white-space:nowrap}th{position:sticky;top:0;z-index:2;padding:11px 9px;border-bottom:1px solid var(--line);background:#050505;color:#fff;font-size:.66rem;text-align:right}th:nth-child(2){text-align:left}td{padding:12px 9px;border-bottom:1px solid var(--soft);font-size:.79rem;text-align:right}td:nth-child(2){text-align:left;font-weight:1000}.click-row{cursor:pointer}.click-row:hover{background:#efffcf}.rank-dot{display:inline-grid;width:27px;height:27px;place-items:center;background:var(--acid);font-weight:1000}.badge{display:inline-block;padding:2px 5px;background:var(--acid);font-size:.57rem;font-weight:1000}.muted{color:var(--muted)}
.compare-add{display:flex;gap:8px;padding:14px;border-bottom:1px solid var(--line)}.compare-add select{flex:1}.action{padding:9px 14px;border:1px solid var(--line);border-radius:0;background:var(--acid);font-weight:1000}.action:hover{background:#050505;color:#fff}.chips{display:flex;flex-wrap:wrap;gap:6px;min-height:35px;margin:15px}.chip{display:inline-flex;align-items:center;gap:7px;padding:5px 8px;border:1px solid var(--line);background:#fff;font-size:.7rem;font-weight:900}.chip button{width:19px;height:19px;padding:0;border:0;background:#050505;color:#fff}.compare-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:22px;padding:18px}.metric h3{margin:0 0 9px;font-size:.8rem}.bar-row{display:grid;grid-template-columns:130px 1fr 42px;align-items:center;gap:8px;margin:8px 0;font-size:.68rem}.bar-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:800}.track{height:12px;background:#e9e9e4;overflow:hidden}.fill{height:100%;background:#050505}.metric:nth-child(2) .fill{background:#6b6b6b}.metric:nth-child(3) .fill{background:var(--acid)}.metric:nth-child(4) .fill{background:#7e5cff}
.trend-panel{margin:22px 0;padding:16px;border:1px solid var(--line);background:#fff}.trend-head{display:flex;align-items:end;justify-content:space-between;gap:12px;margin-bottom:10px}.trend-head h3{margin:0}.trend-legend{display:flex;gap:12px;font-size:.68rem;font-weight:900}.trend-legend i{display:inline-block;width:16px;height:4px;margin-right:5px;vertical-align:middle}.trend-wrap{overflow-x:auto}.trend-wrap canvas{display:block;min-width:560px;width:100%;height:300px}.method{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid var(--line);border-left:1px solid var(--line)}.method article{padding:17px;border-right:1px solid var(--line);border-bottom:1px solid var(--line);background:#fff}.method strong{display:block;margin-bottom:5px;font-size:1rem}footer{padding:38px 0 70px;background:#050505;color:#aaa;font-size:.7rem}
dialog{width:min(840px,calc(100% - 24px));max-height:88vh;padding:0;border:1px solid var(--line);border-radius:0;background:var(--paper);box-shadow:12px 12px 0 var(--acid)}dialog::backdrop{background:rgba(0,0,0,.72)}.modal-head{position:sticky;top:0;z-index:3;display:flex;justify-content:space-between;gap:20px;padding:19px 21px;border-bottom:1px solid #333;background:#050505;color:#fff}.modal-head h2{margin:0;font-size:clamp(1.5rem,4vw,2.6rem);letter-spacing:-.05em}.close{width:38px;height:38px;border:0;background:var(--acid);font-weight:1000}.modal-body{padding:22px}.detail-stats{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid var(--line);border-left:1px solid var(--line);margin-bottom:22px}.detail-stat{padding:12px;border-right:1px solid var(--line);border-bottom:1px solid var(--line);background:#fff}.detail-stat span{display:block;color:var(--muted);font-size:.62rem}.detail-stat strong{font-size:1.3rem}.song-list{display:grid;gap:7px}.song-item{padding:12px;border:1px solid var(--line);background:#fff}.song-title{font-weight:1000}.song-meta{color:var(--muted);font-size:.7rem}.up{color:var(--green)}.down{color:var(--red)}
.control-group{margin-top:24px}.control-heading{display:flex;align-items:baseline;gap:10px;margin-bottom:8px}.control-label{font-size:.75rem;font-weight:1000;letter-spacing:.08em}.control-help{color:#a8a8a8;font-size:.68rem;font-weight:700}.scope-tabs,.chart-tabs{margin-top:0;border-radius:16px}.scope-tabs{display:inline-flex;flex-wrap:wrap;gap:5px;padding:5px}.scope-tab{border-right:0;border-radius:11px}.scope-tab.active{background:var(--acid);color:#050505}.chart-tab{border-radius:11px}.chart-tab.active{background:var(--cyan)}.mark{border-radius:11px}.eyebrow,.pill,.live,.badge{border-radius:999px}.latest-grid,.stats,.method{gap:10px;border:0}.latest-song,.stat,.method article{border:1px solid var(--line);border-radius:18px}.artist-card{border-radius:18px}.panel{overflow:hidden;border-radius:20px}.tools input,.tools select,.compare-add select{border-radius:12px}.action{border-radius:12px}.chip{border-radius:999px}.chip button,.rank-dot{border-radius:50%}.trend-panel{border-radius:18px}.track{border-radius:999px}.fill{border-radius:999px}.song-item,.detail-stat{border-radius:14px}button.song-item{width:100%;text-align:left}.detail-stats{gap:8px;border:0}.detail-stat{border:1px solid var(--line)}dialog{overflow:hidden;border-radius:24px;box-shadow:0 24px 70px rgba(0,0,0,.34),8px 8px 0 var(--acid)}.modal-head>div:first-child{min-width:0}.modal-head h2{overflow-wrap:anywhere}.modal-actions{display:flex;flex:0 0 auto;align-items:center;gap:8px}.share-x{min-height:38px;padding:0 14px;border:1px solid #666;border-radius:999px;background:#fff;color:#050505;font-size:.72rem;font-weight:1000}.share-x:hover{background:var(--cyan)}.close{border-radius:50%}dialog[open]{display:flex;flex-direction:column}.modal-head{flex:0 0 auto}.modal-body{flex:1 1 auto;min-height:0;overflow-y:auto;overscroll-behavior:contain;-webkit-overflow-scrolling:touch}.song-artist-button{display:inline-flex;align-items:center;margin:0 0 18px;padding:8px 13px;border:1px solid var(--line);border-radius:999px;background:var(--acid);font-weight:1000}.song-artist-button:hover{background:var(--cyan)}.song-history{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px}.song-history-item{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:10px 12px;border:1px solid var(--soft);border-radius:12px;background:#fff;font-size:.76rem}.song-history-item strong{font-size:1rem}
@media(max-width:950px){.stats{grid-template-columns:repeat(2,1fr)}.latest-grid{grid-template-columns:repeat(2,1fr)}.card-grid{grid-template-columns:repeat(3,1fr)}.method{grid-template-columns:1fr 1fr}}
@media(max-width:650px){.wrap{width:calc(100% - 20px)}nav a:not(:first-child){display:none}.hero{padding:48px 0 38px}h1{font-size:clamp(3rem,18vw,5.2rem)}.section{padding:36px 0}.section-head{display:block}.section-copy{margin-top:13px}.stats,.latest-grid,.card-grid,.compare-grid,.method,.detail-stats{grid-template-columns:1fr}.artist-card{min-height:0}.panel{border-left:0;border-right:0}.bar-row{grid-template-columns:95px 1fr 35px}.compare-add{display:grid}.compare-grid{padding:14px}.latest-song{min-height:92px}dialog{max-height:92vh}.detail-stats{grid-template-columns:1fr 1fr}}
.share-dialog{width:min(720px,calc(100% - 24px))}.share-view-picker,.share-chart-picker{display:flex;flex-wrap:wrap;gap:7px;padding:18px 20px 0}.share-chart-picker{padding-top:9px}.share-chart-picker[hidden]{display:none}.share-chart-button{padding:8px 12px;border:1px solid #999;border-radius:999px;background:#fff;font-size:.7rem;font-weight:1000}.share-chart-button:hover{background:var(--acid-soft)}.share-chart-button.active{border-color:#111;background:var(--acid);color:#111}.share-preview{padding:18px 20px 0}.share-preview canvas{display:block;width:100%;height:auto;border:1px solid var(--line);border-radius:16px;background:#fffdf8}.share-copy{margin:14px 20px 0;color:var(--muted);font-size:.76rem;font-weight:700}.share-actions{display:grid;grid-template-columns:1fr 1.4fr;gap:10px;padding:16px 20px 20px}.share-action{min-height:46px;padding:10px 15px;border:1px solid var(--line);border-radius:13px;background:#fff;font-weight:1000}.share-action.primary{background:var(--acid)}.share-action:hover{background:var(--cyan)}.share-status{min-height:1.5em;margin:0;padding:0 20px 18px;color:var(--muted);font-size:.75rem;font-weight:800}.share-status.success{color:var(--green)}.share-status.error{color:var(--red)}
.song-rank-caption{margin:4px 0 0;color:var(--muted);font-size:.68rem;font-weight:800}.song-history-heading{margin:22px 0 8px;font-size:.82rem}.song-rank-empty{display:grid;min-height:180px;place-items:center;color:var(--muted);font-size:.76rem;font-weight:800}
@media(max-width:650px){.modal-actions{gap:5px}.share-x{padding:0 10px}.share-actions{grid-template-columns:1fr}.share-preview{padding:14px 14px 0}.share-copy{margin:12px 14px 0}.share-actions{padding:14px}.share-status{padding:0 14px 14px}}
/* Readability refresh: keep the editorial character while clarifying visual hierarchy. */
:root{--paper:#f6f5f0;--ink:#11110f;--muted:#64645f;--line:#292925;--soft:#d8d8d0;--acid-soft:#efffcf;--cyan-soft:#dff8ff;--green:#0b7a4b;--red:#c43d52}
body{background:var(--paper)}.top{background:#11110f;border-bottom-color:#292925}.topin{min-height:62px}.hero{padding:50px 0 44px;background:#11110f;border-bottom-width:6px}.eyebrow{margin-bottom:16px}.hero h1{max-width:920px;font-size:clamp(3.1rem,7.6vw,6.35rem);line-height:.88;letter-spacing:-.075em}.lead{max-width:760px;margin-top:20px;color:#e1e1dc;font-weight:650}
.control-group{margin-top:20px}.control-heading{margin-bottom:7px}.scope-tabs,.chart-tabs{border-color:#555;background:#1b1b19}.scope-tab,.chart-tab{min-height:42px;padding:9px 15px}.scope-tab:hover,.chart-tab:hover{background:#32322f}.scope-tab.active,.chart-tab.active{background:var(--acid);color:#11110f}.fresh{margin-top:14px}.pill{border-color:#4d4d48;background:#191917;color:#eeeeea}
.section{padding:54px 0;background:transparent}.section:nth-of-type(even){background:transparent}.latest-section,#ranking,#compare{background:#fff}#power,#songs,#method{background:var(--paper)}.section-head{margin-bottom:24px;padding-top:14px;border-top:2px solid var(--line)}.latest-section .section-head{border-top-width:4px}.section h2{font-size:clamp(1.9rem,3.6vw,3.15rem);letter-spacing:-.045em}.section-copy{font-size:.88rem;line-height:1.7}.kicker{color:#506f08}
.latest-grid{gap:12px;border:0}.latest-song{min-height:108px;border:1px solid var(--soft);border-radius:16px;box-shadow:0 4px 14px rgba(17,17,15,.04)}.latest-song:hover{background:var(--acid-soft);border-color:#9fcd3c;transform:translateY(-2px)}.latest-title{font-size:.96rem}.latest-artist{font-size:.73rem}.latest-rank{display:grid;width:44px;height:44px;place-items:center;border-radius:50%;background:#11110f;color:#fff;font-size:1rem}
.artist-card{border-color:var(--soft);box-shadow:0 4px 16px rgba(17,17,15,.035)}.artist-card:hover{transform:translateY(-2px);border-color:#9fcd3c;box-shadow:0 10px 24px rgba(17,17,15,.09)}.artist-card h3{font-size:1.18rem}.mini{font-size:.69rem}.live{background:var(--cyan)}
.panel{border-color:var(--soft);box-shadow:0 8px 24px rgba(17,17,15,.04)}.tools{padding:16px;border-bottom-color:var(--soft);background:#fafaf7}.tools input,.tools select,.compare-add select{min-height:44px;border-color:#aaa9a1}.table-wrap{scrollbar-color:#b6b6ae transparent}th{padding:13px 10px;background:#171715;font-size:.71rem;letter-spacing:.02em}td{padding:13px 10px;font-size:.84rem}.click-row:hover{background:var(--acid-soft)}.rank-dot{background:#171715;color:#fff}.badge{background:var(--acid);color:#11110f}
.trend-panel,.song-item,.detail-stat{border-color:var(--soft)}.trend-panel{box-shadow:0 4px 16px rgba(17,17,15,.035)}.method article{border-color:var(--soft)}.action{border-color:#11110f}.action:hover{background:#11110f}.share-action:hover,.share-x:hover,.song-artist-button:hover{background:var(--cyan-soft)}
@media(max-width:650px){.hero{padding:40px 0 34px}.hero h1{font-size:clamp(2.8rem,16vw,4.7rem)}.lead{font-size:.95rem}.topin{gap:10px}.topin nav{display:flex;max-width:calc(100vw - 84px);overflow-x:auto;overscroll-behavior-inline:contain;scrollbar-width:none}.topin nav::-webkit-scrollbar{display:none}.topin nav a,.topin nav a:not(:first-child){display:block;flex:0 0 auto;white-space:nowrap}.control-heading{display:block}.control-help{display:block;margin-top:2px}.scope-tabs,.chart-tabs{display:grid;width:100%;grid-template-columns:1fr}.scope-tab,.chart-tab{width:100%}.section{padding:40px 0}.section-head{padding-top:11px}.latest-grid{gap:9px}th{font-size:.68rem}td{font-size:.81rem}}
@media(max-width:650px){.hero{padding:28px 0 24px}.hero h1{font-size:clamp(2.35rem,13vw,3.85rem)}.lead{margin-top:12px;font-size:.84rem}.control-group{margin-top:11px}.control-heading{margin-bottom:5px}.control-help{display:none}.scope-tabs,.chart-tabs{display:flex;width:100%;grid-template-columns:none;flex-wrap:nowrap;gap:4px;padding:4px;overflow-x:auto;overscroll-behavior-inline:contain;scrollbar-width:none}.scope-tabs::-webkit-scrollbar,.chart-tabs::-webkit-scrollbar{display:none}.scope-tab,.chart-tab{flex:0 0 auto;width:auto;min-height:36px;padding:7px 10px;font-size:.65rem;white-space:nowrap}.latest-viewport{scrollbar-width:none}.latest-viewport::-webkit-scrollbar{display:none}}
/* Progressive lists and latest-chart carousel. */
.latest-carousel{display:grid;grid-template-columns:42px minmax(0,1fr) 42px;align-items:center;gap:10px}.latest-viewport{overflow-x:auto;scroll-behavior:smooth;scroll-snap-type:none;overscroll-behavior-inline:contain;scrollbar-width:none;-ms-overflow-style:none}.latest-viewport::-webkit-scrollbar{display:none}.latest-carousel .latest-grid{display:flex;width:max-content;gap:12px;border:0}.latest-carousel .latest-song{flex:0 0 var(--latest-card-width,340px);width:auto;scroll-snap-align:start}.carousel-button{display:grid;width:42px;height:42px;place-items:center;border:1px solid var(--line);border-radius:50%;background:#fff;font-size:1.25rem;font-weight:1000}.carousel-button:hover{background:var(--acid)}.carousel-button[hidden]{display:none}.list-more{display:flex;align-items:center;justify-content:center;gap:14px;padding:16px;border-top:1px solid var(--soft);background:#fafaf7}.list-count{color:var(--muted);font-size:.75rem;font-weight:800}.ranking-note{margin:-8px 0 18px;padding:10px 12px;border-left:4px solid var(--acid);background:#f5f5f0;color:var(--muted);font-size:.76rem;font-weight:700;line-height:1.65}.more-button{min-height:42px;padding:9px 18px;border:1px solid var(--line);border-radius:12px;background:#fff;font-weight:1000}.more-button:hover{background:var(--acid-soft)}
.search-section{padding:28px 0;background:#111;color:#fff;border-bottom:1px solid #333}.search-shell{display:grid;grid-template-columns:minmax(250px,.8fr) minmax(0,1.2fr);gap:22px;align-items:start}.search-intro .kicker{color:var(--acid)}.search-intro h2{margin:0 0 8px;font-family:Arial Black,Arial,sans-serif;font-size:clamp(1.6rem,3vw,2.45rem);letter-spacing:-.045em}.search-intro p{margin:0;color:#bdbdb8;font-size:.78rem;font-weight:700}.global-search{width:100%;min-height:52px;padding:12px 16px;border:1px solid #777;border-radius:14px;background:#fff;color:#111;font-size:1rem;font-weight:800}.global-search:focus{outline:3px solid var(--acid);outline-offset:2px}.search-status{min-height:1.6em;margin:8px 2px 0;color:#aaa;font-size:.72rem;font-weight:800}.search-results{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}.search-result{display:flex;min-width:0;align-items:center;justify-content:space-between;gap:12px;padding:11px 12px;border:1px solid #555;border-radius:12px;background:#1c1c1c;color:#fff;text-align:left}.search-result:hover,.search-result:focus-visible{border-color:var(--acid);background:#292929}.search-result-main{min-width:0}.search-result-name{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.8rem;font-weight:1000}.search-result-sub{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#aaa;font-size:.66rem}.search-result-type{flex:0 0 auto;padding:3px 7px;border-radius:999px;background:var(--acid);color:#111;font-size:.6rem;font-weight:1000}.detail-chart-switch{display:flex;flex-wrap:wrap;gap:7px;margin:0 0 12px}.detail-chart-button{padding:8px 12px;border:1px solid #999;border-radius:999px;background:#fff;font-size:.7rem;font-weight:1000}.detail-chart-button:hover{background:var(--cyan-soft)}.detail-chart-button.active{border-color:#111;background:#111;color:#fff}.detail-chart-context{margin:0 0 18px;color:var(--muted);font-size:.72rem;font-weight:800}
@media(max-width:650px){.latest-carousel{grid-template-columns:minmax(0,1fr)}.carousel-button{display:none}.latest-carousel .latest-grid{display:grid;grid-auto-flow:column;grid-template-rows:repeat(5,minmax(68px,auto));grid-auto-columns:min(88vw,350px);gap:8px 10px}.latest-carousel .latest-song{width:100%;min-height:68px;padding:10px;grid-template-columns:42px minmax(0,1fr)}.latest-carousel .latest-rank{width:38px;height:38px;font-size:.88rem}.latest-viewport{margin-right:-10px;padding-right:10px}.list-more{align-items:stretch;flex-direction:column;text-align:center}.more-button{width:100%}.search-shell{grid-template-columns:1fr}.search-results{grid-template-columns:1fr}.search-section{padding:24px 0}}
@media(prefers-reduced-motion:reduce){.latest-viewport{scroll-behavior:auto}}
</style>
</head>
<body>
<header class="top"><div class="wrap topin"><a class="brand" href="#top"><span class="mark">JP</span>CHART PULSE</a><nav><a href="#search">検索</a><a href="#latest">最新週</a><a href="#ranking">ランキング</a><a href="#songs">楽曲</a></nav></div></header>
<main id="top">
<section class="hero"><div class="wrap"><p class="eyebrow">BILLBOARD JAPAN / CHART EXPLORER</p><h1>MUSIC<br>IN <span class="slash">MOTION.</span></h1><p class="lead">順位の変化や継続をたどりながら、アーティストと楽曲の現在地を多角的に見ていく。</p><div class="control-group"><div class="control-heading"><span class="control-label">表示するアーティスト</span><span class="control-help">分析対象の範囲を選択</span></div><div class="scope-tabs" role="tablist" aria-label="表示するアーティストの範囲を切り替える"><button class="scope-tab active" data-scope="boys">ボーイズグループ</button><button class="scope-tab" data-scope="girls">ガールズグループ</button><button class="scope-tab" data-scope="korean">K-POPグループ</button><button class="scope-tab" data-scope="all">全アーティスト</button></div></div><div class="control-group"><div class="control-heading"><span class="control-label">集計するチャート</span><span class="control-help">総合・ストリーミング・ダウンロードから選択</span></div><div class="chart-tabs" role="tablist" aria-label="集計するチャートを切り替える"><button class="chart-tab active" data-chart="hot100">総合 Hot 100</button><button class="chart-tab" data-chart="stsongs">ストリーミング</button><button class="chart-tab" data-chart="dlsongs">ダウンロード</button></div></div><span id="scopeName" hidden>ボーイズグループ</span><span id="chartName" hidden>Billboard Japan Hot 100</span></div></section>
<section class="search-section" id="search"><div class="wrap search-shell"><div class="search-intro"><p class="kicker">SEARCH ALL DATA</p><h2>アーティスト・楽曲検索</h2><p>表示中のカテゴリやランキング表示数に関係なく、すべての集計対象を横断して検索できます。</p></div><div><label class="control-label" for="globalSearch">名前・曲名から探す</label><input class="global-search" id="globalSearch" type="search" autocomplete="off" placeholder="アーティスト名、楽曲名"><input id="artistSearch" type="search" hidden tabindex="-1" aria-hidden="true"><input id="songSearch" type="search" hidden tabindex="-1" aria-hidden="true"><p class="search-status" id="searchStatus" aria-live="polite">文字を入力すると候補を表示します。</p><div class="search-results" id="searchResults"></div></div></div></section>
<section class="section latest-section" id="latest"><div class="wrap"><div class="section-head"><div><p class="kicker">LATEST CHART</p><h2>最新週のランクイン楽曲</h2></div><p class="section-copy"><span id="latestChartName">Billboard Japan Hot 100</span>・<span id="latestWeek">__LATEST_DATE__</span>公開分。今週チャートにいる対象アーティストの楽曲を順位順に表示します。</p></div><div class="latest-carousel"><button class="carousel-button" id="latestPrev" type="button" aria-label="前の楽曲を見る">‹</button><div class="latest-viewport" id="latestViewport" tabindex="0" aria-label="最新週のランクイン楽曲。横にスクロールできます"><div class="latest-grid" id="latestGrid"></div></div><button class="carousel-button" id="latestNext" type="button" aria-label="次の楽曲を見る">›</button></div></div></section>
<div id="stats" hidden></div><div id="powerGrid" hidden></div>
<section class="section" id="ranking"><div class="wrap"><div class="section-head"><div><p class="kicker">TOP 50 ARTISTS</p><h2>アーティストランキング</h2></div><p class="section-copy">年間の延べ登場回数を軸に、存在感・継続力・ヒットの強さを確認できます。行を押すと詳細が開きます。</p></div><p class="ranking-note">※ <span id="artistRankingYear">2026</span>年に一度でもランクインした対象のうち、集計指標の上位50組までを表示します。圏外のアーティストは上部の横断検索から探せます。</p><div class="panel"><div class="tools"><select id="artistFilter" aria-label="アーティストランキングの絞り込み"><option value="all">すべて</option><option value="active">最新週ランクイン中</option><option value="rising">前年同期より増加</option><option value="top10">Top 10実績あり</option></select></div><div class="table-wrap"><table><thead><tr><th>順位</th><th>アーティスト</th><th>延べ登場</th><th>登場週</th><th>楽曲</th><th>Top 10</th><th>最高</th><th>前年同期比</th></tr></thead><tbody id="artistRows"></tbody></table></div><div class="list-more"><span class="list-count" id="artistCount"></span><button class="more-button" id="artistMore" type="button">もっと見る</button></div></div></div></section>
<section class="section" id="songs"><div class="wrap"><div class="section-head"><div><p class="kicker">HIT SONGS</p><h2>ヒット曲ランキング</h2></div><p class="section-copy">どの曲がアーティストの存在感を作ったのか。延べ登場回数順に表示します。</p></div><p class="ranking-note">※ <span id="songRankingYear">2026</span>年に一度でもランクインした楽曲のうち、上位100曲までを表示します。圏外の楽曲は上部の横断検索から探せます。</p><div class="panel"><div class="table-wrap"><table><thead><tr><th>順位</th><th>曲名</th><th>アーティスト</th><th>延べ登場</th><th>登場週</th><th>最高順位</th><th>Top 10</th></tr></thead><tbody id="songRows"></tbody></table></div><div class="list-more"><span class="list-count" id="songCount"></span><button class="more-button" id="songMore" type="button">もっと見る</button></div></div></div></section>

</main>
<footer><div class="wrap">集計対象: Billboard Japan Hot 100・Streaming Songs・Download Songs / 1〜100位　生成: __GENERATED_AT__<br>本サイトは公式Billboardサイトではありません。順位データの権利は各権利者に帰属します。</div></footer>
<dialog id="detailDialog"><div class="modal-head"><div><div class="kicker">ARTIST DETAIL</div><h2 id="detailName"></h2></div><div class="modal-actions"><button class="share-x" id="openShare" type="button" aria-label="このアーティストの詳細を共有">共有</button><button id="shareX" type="button" hidden aria-hidden="true" tabindex="-1"></button><button class="close" id="detailClose" aria-label="閉じる">×</button></div></div><div class="modal-body"><div class="detail-chart-switch" id="detailChartSwitch" role="tablist" aria-label="アーティスト詳細のチャートを切り替える"><button class="detail-chart-button" type="button" data-detail-chart="hot100">Hot 100</button><button class="detail-chart-button" type="button" data-detail-chart="stsongs">ストリーミング</button><button class="detail-chart-button" type="button" data-detail-chart="dlsongs">ダウンロード</button></div><p class="detail-chart-context" id="detailChartContext"></p><div class="detail-stats" id="detailStats"></div><section class="trend-panel"><div class="trend-head"><div><div class="kicker">WEEK BY WEEK</div><h3>2024〜2026年の累積推移</h3></div><div class="trend-legend"><span><i style="background:#6b7280"></i>2024</span><span><i style="background:#0072b2"></i>2025</span><span><i style="background:#d55e00"></i>2026</span></div></div><div class="trend-wrap"><canvas id="yearTrend" aria-label="2024年から2026年の週別累積ランクイン数"></canvas></div></section><h3>2026年の楽曲</h3><div class="song-list" id="detailSongs"></div></div></dialog>
<dialog class="share-dialog" id="shareDialog"><div class="modal-head"><div><div class="kicker" id="shareKind">SHARE PROFILE</div><h2 id="shareTitle">共有</h2></div><button class="close" id="shareClose" aria-label="共有画面を閉じる">×</button></div><div class="modal-body"><div class="share-view-picker" id="shareViewPicker" role="tablist" aria-label="共有画像の種類を選択"><button class="share-chart-button active" type="button" data-share-view="summary">概要</button><button class="share-chart-button" type="button" data-share-view="graph">グラフ</button></div><div class="share-chart-picker" id="shareChartPicker" role="tablist" aria-label="共有画像に使うチャートを選択" hidden><button class="share-chart-button" type="button" data-share-chart="hot100">Hot 100</button><button class="share-chart-button" type="button" data-share-chart="stsongs">ストリーミング</button><button class="share-chart-button" type="button" data-share-chart="dlsongs">ダウンロード</button></div><div class="share-preview"><canvas id="shareCard" width="1200" height="630" aria-label="共有用の詳細画像"></canvas></div><p class="share-copy">グラフなしの概要画像と、詳細画面をもとにしたグラフ画像を選べます。アーティストは対象チャートも変更できます。</p><div class="share-actions"><button class="share-action" id="copyShareLink" type="button">リンクをコピー</button><button class="share-action primary" id="shareWithImage" type="button">Xへ画像付き共有</button></div><p class="share-status" id="shareStatus" role="status" aria-live="polite"></p></div></dialog>
<dialog id="songDialog"><div class="modal-head"><div><div class="kicker">SONG DETAIL</div><h2 id="songDetailTitle"></h2></div><div class="modal-actions"><button class="share-x" id="openSongShare" type="button" aria-label="この楽曲の詳細を共有">共有</button><button class="close" id="songDetailClose" aria-label="閉じる">×</button></div></div><div class="modal-body"><button class="song-artist-button" id="songDetailArtist" type="button"></button><p class="song-meta" id="songDetailChart"></p><div class="detail-stats" id="songDetailStats"></div><section class="trend-panel"><div class="trend-head"><div><div class="kicker">CHART TREND</div><h3>週ごとの順位推移</h3><p class="song-rank-caption">1位に近いほど上に表示。ランク外の期間は線をつなぎません。</p></div></div><div class="trend-wrap" id="songRankTrendWrap"><canvas id="songRankTrend" aria-label="楽曲の週別順位推移"></canvas></div><h4 class="song-history-heading">順位データ</h4><div class="song-history" id="songDetailHistory"></div></section></div></dialog>
<script>
const dashboards=__DASHBOARD_DATA__;let scopeCode="boys";let chartCode="hot100";let dashboard=dashboards[scopeCode][chartCode];let artists=dashboard.artists;let artistDetails=dashboard.artistDetails;let songs=dashboard.songs;let latestSongs=dashboard.latestSongs;let artistExpanded=false;let songDisplayLimit=5;const fmt=n=>n==null?"—":n.toLocaleString("ja-JP");const signed=n=>n>0?`+${n}`:`${n}`;const cls=n=>n>0?"up":n<0?"down":"muted";const esc=v=>String(v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let latestAutoPausedUntil=0,latestAutoHover=false,latestAutoFocus=false,latestAutoTouching=false,latestAutoLast=0,latestAutoCycleWidth=0;const latestFinePointer=matchMedia("(hover:hover) and (pointer:fine)");function pauseLatestAuto(delay=5000){latestAutoPausedUntil=performance.now()+delay}function latestAutoIsPaused(){return latestAutoHover||latestAutoTouching||latestAutoFocus&&latestFinePointer.matches||performance.now()<latestAutoPausedUntil}function latestCardMarkup(song,isCopy=false){const copyAttrs=isCopy?' data-loop-copy="true" aria-hidden="true" tabindex="-1"':'';return `<button class="latest-song"${copyAttrs} data-song-title="${esc(song.title)}" data-song-artist="${esc(song.artist)}"><span class="latest-rank">#${song.latestRank}</span><span><span class="latest-title">${esc(song.title)}</span><span class="latest-artist">${esc(song.artist)}</span></span></button>`}function syncLatestCarousel(){requestAnimationFrame(()=>{const viewport=document.getElementById("latestViewport"),grid=document.getElementById("latestGrid"),copies=[...grid.querySelectorAll("[data-loop-copy]")];grid.style.setProperty("--latest-card-width",Math.max(220,(viewport.clientWidth-24)/3)+"px");copies.forEach(copy=>copy.hidden=false);requestAnimationFrame(()=>{const first=grid.querySelector(".latest-song:not([data-loop-copy])"),copyFirst=grid.querySelector("[data-loop-copy]");latestAutoCycleWidth=first&&copyFirst?copyFirst.offsetLeft-first.offsetLeft:0;const hasOverflow=latestAutoCycleWidth>viewport.clientWidth+4;copies.forEach(copy=>copy.hidden=!hasOverflow);if(!hasOverflow)latestAutoCycleWidth=0;document.getElementById("latestPrev").hidden=!hasOverflow;document.getElementById("latestNext").hidden=!hasOverflow;viewport.scrollLeft=0;latestAutoLast=0})})}function renderLatest(){document.getElementById("latestChartName").textContent=dashboard.chartName;document.getElementById("latestWeek").textContent=dashboard.latestDate;const grid=document.getElementById("latestGrid"),originals=latestSongs.map(song=>latestCardMarkup(song)).join(""),copies=latestSongs.length>1?latestSongs.map(song=>latestCardMarkup(song,true)).join(""):"";grid.innerHTML=latestSongs.length?originals+copies:'<p class="muted">対象アーティストのランクイン楽曲はありません。</p>';syncLatestCarousel()}
function initLatestCarousel(){const viewport=document.getElementById("latestViewport"),step=direction=>{pauseLatestAuto(800);const distance=Math.max(260,viewport.clientWidth*.78);if(direction<0&&latestAutoCycleWidth&&viewport.scrollLeft<distance)viewport.scrollLeft+=latestAutoCycleWidth;viewport.scrollBy({left:direction*distance,behavior:"smooth"})};document.getElementById("latestPrev").addEventListener("click",()=>step(-1));document.getElementById("latestNext").addEventListener("click",()=>step(1));viewport.addEventListener("pointerenter",()=>{latestAutoHover=true});viewport.addEventListener("pointerleave",()=>{latestAutoHover=false});viewport.addEventListener("focusin",()=>{latestAutoFocus=true});viewport.addEventListener("focusout",()=>{latestAutoFocus=false});viewport.addEventListener("touchstart",()=>{latestAutoTouching=true;latestAutoFocus=false},{passive:true});const finishTouch=()=>{latestAutoTouching=false;pauseLatestAuto(2500)};viewport.addEventListener("touchend",finishTouch,{passive:true});viewport.addEventListener("touchcancel",finishTouch,{passive:true});viewport.addEventListener("wheel",()=>pauseLatestAuto(),{passive:true});let resizeTimer=0;window.addEventListener("resize",()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(syncLatestCarousel,140)});if(!matchMedia("(prefers-reduced-motion: reduce)").matches){viewport.style.scrollBehavior="auto";const animate=now=>{const elapsed=latestAutoLast?Math.min(now-latestAutoLast,50):0;latestAutoLast=now;if(!latestAutoIsPaused()&&!document.hidden&&latestAutoCycleWidth>0){viewport.scrollLeft+=30*elapsed/1000;if(viewport.scrollLeft>=latestAutoCycleWidth)viewport.scrollLeft-=latestAutoCycleWidth}requestAnimationFrame(animate)};requestAnimationFrame(animate)}}function renderStats(){const active=artists.filter(a=>a.active).length,total=artists.reduce((s,a)=>s+a.appearances,0),top=artists[0],rising=[...artists].sort((a,b)=>b.ytdChange-a.ytdChange)[0];document.getElementById("stats").innerHTML=`<article class="stat"><div class="stat-label">2026年の存在感トップ</div><div class="stat-value">${esc(top.artist)}</div><div class="stat-note">延べ${fmt(top.appearances)}回</div></article><article class="stat"><div class="stat-label">最新週ランクイン中</div><div class="stat-value">${active}組</div><div class="stat-note">${dashboard.latestDate} 公開分</div></article><article class="stat"><div class="stat-label">表示中アーティスト総登場数</div><div class="stat-value">${fmt(total)}回</div><div class="stat-note">${dashboard.weeks2026}週分</div></article><article class="stat"><div class="stat-label">前年同期比の伸びトップ</div><div class="stat-value">${esc(rising.artist)}</div><div class="stat-note ${cls(rising.ytdChange)}">${signed(rising.ytdChange)}回</div></article>`}
function card(a){return `<button class="artist-card" data-artist="${esc(a.artist)}">${a.active?'<span class="live">CHARTING NOW</span>':''}<span class="card-rank">#${a.rank}</span><h3>${esc(a.artist)}</h3><div class="big-number">${fmt(a.appearances)}</div><div class="muted">延べ登場回数</div><div class="mini-grid"><div class="mini">登場週<strong>${a.weeks}</strong></div><div class="mini">楽曲<strong>${a.songsCount}</strong></div><div class="mini">Top 10<strong>${a.top10}</strong></div><div class="mini">最高順位<strong>${a.best?`#${a.best}`:'—'}</strong></div></div></button>`}
function renderPower(){document.getElementById("powerGrid").innerHTML=artists.slice(0,5).map(card).join("")}

const chartOrder=["hot100","stsongs","dlsongs"];function chartLabel(code){return({hot100:"Hot 100",stsongs:"ストリーミング",dlsongs:"ダウンロード"}[code]||code)}function normalized(value){return String(value||"").normalize("NFKC").toLowerCase()}function globalSearchData(){const artistMap=new Map(),songMap=new Map();chartOrder.forEach(code=>{const details=dashboards[scopeCode]?.[code]?.artistDetails||[];details.forEach(artist=>{if(!artist?.artist)return;let artistEntry=artistMap.get(artist.artist);if(!artistEntry){artistEntry={artist:artist.artist,charts:new Set};artistMap.set(artist.artist,artistEntry)}artistEntry.charts.add(code);(artist.songs||[]).forEach(song=>{if(!song?.title)return;const key=artist.artist+"\u0000"+song.title;let songEntry=songMap.get(key);if(!songEntry){songEntry={artist:artist.artist,title:song.title,charts:new Set};songMap.set(key,songEntry)}songEntry.charts.add(code)})})});return{artists:[...artistMap.values()],songs:[...songMap.values()]}}function resultPriority(value,query){const text=normalized(value);return text===query?0:text.startsWith(query)?1:2}function preferredChart(charts){return charts.has(chartCode)?chartCode:chartOrder.find(code=>charts.has(code))||chartCode}function renderGlobalSearch(){const input=document.getElementById("globalSearch"),results=document.getElementById("searchResults"),status=document.getElementById("searchStatus"),query=normalized(input.value).trim();if(!query){results.innerHTML="";status.textContent="文字を入力すると候補を表示します。";return}const index=globalSearchData(),matchedArtists=index.artists.filter(item=>normalized(item.artist).includes(query)).sort((a,b)=>resultPriority(a.artist,query)-resultPriority(b.artist,query)||a.artist.localeCompare(b.artist,"ja")),matchedSongs=index.songs.filter(item=>normalized(item.title+" "+item.artist).includes(query)).sort((a,b)=>resultPriority(a.title,query)-resultPriority(b.title,query)||a.title.localeCompare(b.title,"ja")),visibleArtists=matchedArtists.slice(0,12),visibleSongs=matchedSongs.slice(0,18);status.textContent=`アーティスト ${matchedArtists.length}組・楽曲 ${matchedSongs.length}曲が見つかりました${matchedArtists.length>12||matchedSongs.length>18?"（関連度の高い候補を表示）":""}`;results.innerHTML=visibleArtists.map(item=>`<button class="search-result" type="button" data-artist="${esc(item.artist)}" data-search-chart="${preferredChart(item.charts)}"><span class="search-result-main"><span class="search-result-name">${esc(item.artist)}</span><span class="search-result-sub">${[...item.charts].map(chartLabel).join(" / ")}</span></span><span class="search-result-type">ARTIST</span></button>`).join("")+visibleSongs.map(item=>`<button class="search-result" type="button" data-song-title="${esc(item.title)}" data-song-artist="${esc(item.artist)}" data-search-chart="${preferredChart(item.charts)}"><span class="search-result-main"><span class="search-result-name">${esc(item.title)}</span><span class="search-result-sub">${esc(item.artist)} ・ ${[...item.charts].map(chartLabel).join(" / ")}</span></span><span class="search-result-type">SONG</span></button>`).join("");if(!results.innerHTML)results.innerHTML='<p class="search-status">一致するデータはありません。</p>'}function rankingYear(){return String(dashboard.latestDate||"").slice(0,4)}function rankedArtistsForYear(){const year=rankingYear();return artists.filter(a=>(a.yearCounts?.[year]??a.appearances??0)>0).slice(0,50)}function rankedSongsForYear(){const year=rankingYear(),ranked=artistDetails.flatMap(artist=>(artist.songs||[]).flatMap(song=>{const history=(song.history||[]).filter(item=>String(item.date||"").slice(0,4)===year);if(!history.length)return[];return[{...song,artist:artist.artist,history,appearances:history.length,weeks:new Set(history.map(item=>item.date)).size,best:Math.min(...history.map(item=>item.rank)),top10:history.filter(item=>item.rank<=10).length,latest:history[history.length-1].date}]}));return ranked.sort((a,b)=>b.appearances-a.appearances||b.weeks-a.weeks||a.best-b.best||a.artist.localeCompare(b.artist,"ja")||a.title.localeCompare(b.title,"ja")).slice(0,100).map((song,index)=>({...song,rankingPosition:index+1}))}function renderArtists(){const year=rankingYear(),f=document.getElementById("artistFilter").value,data=rankedArtistsForYear().filter(a=>f==="all"||f==="active"&&a.active||f==="rising"&&a.ytdChange>0||f==="top10"&&a.top10>0),showAll=f!=="all"||artistExpanded,visible=showAll?data:data.slice(0,5),button=document.getElementById("artistMore");document.getElementById("artistRankingYear").textContent=year;document.getElementById("artistRows").innerHTML=visible.map(a=>`<tr class="click-row" data-artist="${esc(a.artist)}"><td><span class="rank-dot">${a.rank}</span></td><td>${esc(a.artist)} ${a.active?'<span class="badge">NOW</span>':''}</td><td>${fmt(a.appearances)}</td><td>${a.weeks}</td><td>${a.songsCount}</td><td>${a.top10}</td><td>${a.best?`#${a.best}`:'—'}</td><td class="${cls(a.ytdChange)}">${signed(a.ytdChange)}</td></tr>`).join("");document.getElementById("artistCount").textContent=`${visible.length} / ${data.length}組を表示（最大50組）`;button.hidden=f!=="all"||data.length<=5;button.textContent=artistExpanded?"上位5組に戻す":"もっと見る"}
function renderSongs(){const year=rankingYear(),data=rankedSongsForYear(),limit=Math.min(songDisplayLimit,data.length),visible=data.slice(0,limit),button=document.getElementById("songMore");document.getElementById("songRankingYear").textContent=year;document.getElementById("songRows").innerHTML=visible.map(s=>`<tr class="click-row" data-song-title="${esc(s.title)}" data-song-artist="${esc(s.artist)}"><td><span class="rank-dot">${s.rankingPosition}</span></td><td>${esc(s.title)}</td><td>${esc(s.artist)}</td><td>${s.appearances}</td><td>${s.weeks}</td><td>#${s.best}</td><td>${s.top10}</td></tr>`).join("");document.getElementById("songCount").textContent=`${visible.length} / ${data.length}曲を表示（最大100曲）`;button.hidden=data.length<=5;button.textContent=songDisplayLimit>=data.length?"上位5曲に戻す":"もっと見る"}
document.getElementById("artistMore").addEventListener("click",()=>{artistExpanded=!artistExpanded;renderArtists()});document.getElementById("songMore").addEventListener("click",()=>{const total=rankedSongsForYear().length;songDisplayLimit=songDisplayLimit>=total?5:total;renderSongs()});
function drawYearTrend(a){const canvas=document.getElementById("yearTrend"),ratio=window.devicePixelRatio||1,width=Math.max(canvas.parentElement.clientWidth,560),height=300;canvas.width=width*ratio;canvas.height=height*ratio;canvas.style.width=`${width}px`;canvas.style.height=`${height}px`;const context=canvas.getContext("2d");context.setTransform(ratio,0,0,ratio,0,0);context.clearRect(0,0,width,height);const left=48,right=20,top=20,bottom=36,graphWidth=width-left-right,graphHeight=height-top-bottom,v24=a.weeklyCumulative["2024"],v25=a.weeklyCumulative["2025"],v26=a.weeklyCumulative["2026"],maximum=Math.max(...v24,...v25,...v26,1),rounded=Math.ceil(maximum/10)*10||10;context.font="11px sans-serif";context.fillStyle="#6b6b67";context.strokeStyle="rgba(18,18,18,.12)";context.lineWidth=1;for(let step=0;step<=4;step+=1){const value=rounded*step/4,y=top+graphHeight-(value/rounded*graphHeight);context.beginPath();context.moveTo(left,y);context.lineTo(width-right,y);context.stroke();context.textAlign="right";context.textBaseline="middle";context.fillText(Math.round(value),left-8,y)}[1,13,26,39,53].forEach(week=>{const x=left+(week-1)/52*graphWidth;context.textAlign="center";context.textBaseline="top";context.fillText(`第${week}週`,x,height-bottom+10)});function line(values,color){context.beginPath();values.forEach((value,index)=>{const x=left+index/52*graphWidth,y=top+graphHeight-(value/rounded*graphHeight);if(index===0)context.moveTo(x,y);else context.lineTo(x,y)});context.strokeStyle=color;context.lineWidth=3;context.lineJoin="round";context.lineCap="round";context.stroke();const last=values.length-1,x=left+last/52*graphWidth,y=top+graphHeight-(values[last]/rounded*graphHeight);context.fillStyle=color;context.beginPath();context.arc(x,y,4,0,Math.PI*2);context.fill()}line(v24,"#6b7280");line(v25,"#0072b2");line(v26,"#d55e00")}
function findSongDetail(artist,title){const artistData=artistDetails.find(a=>a.artist===artist),historySong=artistData?.songs.find(s=>s.title===title),summary=songs.find(s=>s.artist===artist&&s.title===title),latest=latestSongs.find(s=>s.artist===artist&&s.title===title);if(!historySong&&!summary&&!latest)return null;return{artist,title,...(summary||{}),...(historySong||{}),...(latest||{}),history:historySong?.history||[]}}function openSongDetail(artist,title){const artistDialog=document.getElementById("detailDialog");if(artistDialog.open)artistDialog.close();const s=findSongDetail(artist,title);if(!s)return;const history=s.history||[],last=history.length?history[history.length-1]:null,first=history.length?history[0]:null,latestRank=s.latestRank??(last&&last.date===dashboard.latestDate?last.rank:null);document.getElementById("songDetailTitle").textContent=s.title;const artistButton=document.getElementById("songDetailArtist");artistButton.textContent=s.artist+" のArtist Detailへ";artistButton.dataset.artistName=s.artist;document.getElementById("songDetailChart").textContent=dashboard.chartName+"・"+(first?first.date+"〜"+last.date:"順位履歴なし");const stats=[["最新順位",latestRank?"#"+latestRank:"—"],["最高順位",s.best?"#"+s.best:"—"],["延べ登場",(s.appearances??history.length)+"回"],["登場週",(s.weeks??history.length)+"週"],["Top 10",(s.top10??history.filter(h=>h.rank<=10).length)+"回"],["最終登場",s.latest??(last?last.date:"—")]];document.getElementById("songDetailStats").innerHTML=stats.map(([label,value])=>"<div class=\"detail-stat\"><span>"+esc(label)+"</span><strong>"+esc(value)+"</strong></div>").join("");document.getElementById("songDetailHistory").innerHTML=history.length?[...history].reverse().map(h=>"<div class=\"song-history-item\"><span>"+esc(h.date)+"</span><strong>#"+h.rank+"</strong></div>").join(""):"<p class=\"muted\">週別の順位履歴はありません。</p>";const dialog=document.getElementById("songDialog");if(!dialog.open)dialog.showModal()}let currentArtistName="";function artistShareUrl(name){const base=location.href.split("#")[0],params=new URLSearchParams({artist:name,scope:scopeCode,chart:chartCode});return base+"#"+params.toString()}function openDetail(name,updateUrl=true){const a=artistDetails.find(x=>x.artist===name);if(!a)return;currentArtistName=a.artist;if(updateUrl)history.replaceState(null,"",artistShareUrl(a.artist));document.getElementById("detailName").textContent=a.artist;const stats=[['延べ登場',a.appearances+'回'],['登場週',a.weeks+'週'],['ランクイン曲',a.songsCount+'曲'],['Top 10',a.top10+'回'],['最高順位',a.best?'#'+a.best:'—'],['前年同期比',signed(a.ytdChange)]];document.getElementById("detailStats").innerHTML=stats.map(([l,v])=>`<div class="detail-stat"><span>${l}</span><strong>${v}</strong></div>`).join('');document.getElementById("detailSongs").innerHTML=a.songs.length?a.songs.map(s=>`<button class="song-item" type="button" data-song-title="${esc(s.title)}" data-song-artist="${esc(a.artist)}"><div class="song-title">${esc(s.title)}</div><div class="song-meta">延べ${s.appearances}回・${s.weeks}週・最高#${s.best}・最終登場 ${s.latest}</div></button>`).join(''):'<p class="muted">2026年のランクイン曲はありません。</p>';const dialog=document.getElementById("detailDialog");if(!dialog.open)dialog.showModal();requestAnimationFrame(()=>drawYearTrend(a))}document.addEventListener("click",e=>{const songTarget=e.target.closest("[data-song-title]");if(songTarget)openSongDetail(songTarget.dataset.songArtist,songTarget.dataset.songTitle);else{const target=e.target.closest("[data-artist]");if(target)openDetail(target.dataset.artist)}});document.getElementById("artistSearch").addEventListener("input",renderArtists);document.getElementById("artistFilter").addEventListener("change",renderArtists);document.getElementById("songSearch").addEventListener("input",renderSongs);const songDialog=document.getElementById("songDialog");document.getElementById("songDetailClose").addEventListener("click",()=>songDialog.close());songDialog.addEventListener("click",e=>{if(e.target===e.currentTarget)e.currentTarget.close()});document.getElementById("songDetailArtist").addEventListener("click",e=>{const name=e.currentTarget.dataset.artistName;songDialog.close();if(name)openDetail(name)});document.getElementById("shareX").addEventListener("click",()=>{if(!currentArtistName)return;const query=new URLSearchParams({text:currentArtistName+"のBillboard JAPANチャート推移をチェック",url:artistShareUrl(currentArtistName)});window.open("https://twitter.com/intent/tweet?"+query.toString(),"_blank","noopener,noreferrer,width=640,height=520")});const detailDialog=document.getElementById("detailDialog");document.getElementById("detailClose").addEventListener("click",()=>detailDialog.close());detailDialog.addEventListener("click",e=>{if(e.target===e.currentTarget)e.currentTarget.close()});detailDialog.addEventListener("close",()=>{currentArtistName="";history.replaceState(null,"",location.href.split("#")[0])});function applyDashboard(){dashboard=dashboards[scopeCode][chartCode];artists=dashboard.artists;artistDetails=dashboard.artistDetails;songs=dashboard.songs;latestSongs=dashboard.latestSongs;document.getElementById("scopeName").textContent=({boys:"ボーイズグループ",girls:"ガールズグループ",all:"全アーティスト"}[scopeCode]);document.getElementById("chartName").textContent=dashboard.chartName;document.querySelectorAll("[data-chart]").forEach(button=>button.classList.toggle("active",button.dataset.chart===chartCode));document.querySelectorAll("[data-scope]").forEach(button=>button.classList.toggle("active",button.dataset.scope===scopeCode));renderLatest();renderStats();renderPower();renderArtists();renderSongs()}
function drawSongRankTrend(rawHistory){const canvas=document.getElementById("songRankTrend"),ratio=window.devicePixelRatio||1,width=Math.max(canvas.parentElement.clientWidth,560),height=300;canvas.width=width*ratio;canvas.height=height*ratio;canvas.style.width=`${width}px`;canvas.style.height=`${height}px`;const context=canvas.getContext("2d");context.setTransform(ratio,0,0,ratio,0,0);context.clearRect(0,0,width,height);const history=[...rawHistory].sort((a,b)=>a.date.localeCompare(b.date));if(!history.length){context.fillStyle="#686868";context.font="700 13px sans-serif";context.textAlign="center";context.textBaseline="middle";context.fillText("順位推移データはありません",width/2,height/2);return}const left=52,right=22,top=24,bottom=48,graphWidth=width-left-right,graphHeight=height-top-bottom,times=history.map(item=>new Date(item.date+"T00:00:00Z").getTime()),minimum=times[0],maximum=times[times.length-1],xFor=time=>maximum===minimum?left+graphWidth/2:left+(time-minimum)/(maximum-minimum)*graphWidth,yFor=rank=>top+(Math.max(1,Math.min(100,rank))-1)/99*graphHeight;context.fillStyle="rgba(184,255,37,.18)";context.fillRect(left,top,graphWidth,yFor(10)-top);context.font="11px sans-serif";context.lineWidth=1;[1,10,25,50,75,100].forEach(rank=>{const y=yFor(rank);context.strokeStyle=rank===10?"rgba(87,123,0,.45)":"rgba(18,18,18,.12)";context.beginPath();context.moveTo(left,y);context.lineTo(width-right,y);context.stroke();context.fillStyle="#6b6b67";context.textAlign="right";context.textBaseline="middle";context.fillText("#"+rank,left-8,y)});const labelIndexes=[0,Math.round((history.length-1)*.25),Math.round((history.length-1)*.5),Math.round((history.length-1)*.75),history.length-1];[...new Set(labelIndexes)].forEach(index=>{const item=history[index],x=xFor(times[index]),date=new Date(item.date+"T00:00:00Z");context.fillStyle="#6b6b67";context.textAlign="center";context.textBaseline="top";context.fillText((date.getUTCMonth()+1)+"/"+date.getUTCDate(),x,height-bottom+12)});context.strokeStyle="#0072b2";context.lineWidth=3;context.lineJoin="round";context.lineCap="round";context.beginPath();history.forEach((item,index)=>{const x=xFor(times[index]),y=yFor(item.rank),gap=index?times[index]-times[index-1]:0;if(index===0||gap>9*24*60*60*1000)context.moveTo(x,y);else context.lineTo(x,y)});context.stroke();history.forEach((item,index)=>{const x=xFor(times[index]),y=yFor(item.rank);context.fillStyle=item.rank<=10?"#b8ff25":"#25d8ff";context.strokeStyle="#050505";context.lineWidth=2;context.beginPath();context.arc(x,y,5,0,Math.PI*2);context.fill();context.stroke();if(history.length<=12){context.fillStyle="#050505";context.font="800 10px sans-serif";context.textAlign="center";context.textBaseline="bottom";context.fillText("#"+item.rank,x,y-8)}})}
let handlingHistoryPop=false,artistHistoryActive=false,songHistoryActive=false;
const openDetailWithoutHistory=openDetail;
openDetail=(name,updateUrl=true)=>{if(!artistDetails.some(a=>a.artist===name))return;if(updateUrl){const base=location.href.split("#")[0];history.replaceState(null,"",base);history.pushState({modal:"artist",artist:name,scope:scopeCode,chart:chartCode},"",artistShareUrl(name));artistHistoryActive=true}openDetailWithoutHistory(name,false)};
function songShareUrl(artist,title){const base=location.href.split("#")[0],params=new URLSearchParams({song:title,songArtist:artist,scope:scopeCode,chart:chartCode});return base+"#"+params.toString()}
const openSongDetailWithoutTrend=openSongDetail;
openSongDetail=(artist,title,updateUrl=true)=>{const song=findSongDetail(artist,title);if(!song)return;currentSongShare=song;openSongDetailWithoutTrend(artist,title);if(updateUrl){const base=location.href.split("#")[0];history.replaceState(null,"",base);history.pushState({modal:"song",song:title,songArtist:artist,scope:scopeCode,chart:chartCode},"",songShareUrl(artist,title));songHistoryActive=true}requestAnimationFrame(()=>drawSongRankTrend(song.history||[]))};
detailDialog.addEventListener("close",()=>{const movingToSong=songDialog.open;if(artistHistoryActive&&!handlingHistoryPop&&!movingToSong){artistHistoryActive=false;history.back()}else if(movingToSong)artistHistoryActive=false});
songDialog.addEventListener("close",()=>{const movingToArtist=detailDialog.open;if(songHistoryActive&&!handlingHistoryPop&&!movingToArtist){songHistoryActive=false;history.back()}else if(movingToArtist)songHistoryActive=false});
addEventListener("popstate",()=>{handlingHistoryPop=true;artistHistoryActive=false;songHistoryActive=false;if(detailDialog.open)detailDialog.close();if(songDialog.open)songDialog.close();setTimeout(()=>{handlingHistoryPop=false},0)});
function scopeLabel(){return({boys:"ボーイズグループ",girls:"ガールズグループ",korean:"K-POPグループ",all:"全アーティスト"}[scopeCode])}
let currentShareTarget=null,currentSongShare=null;
function setShareStatus(message,type=""){const status=document.getElementById("shareStatus");status.textContent=message;status.className="share-status"+(type?" "+type:"")}
const shareCanvasFont='Arial, "Yu Gothic UI", "Hiragino Kaku Gothic ProN", sans-serif';
function fitCanvasText(context,text,maxWidth,startSize,minSize,weight=900){let size=startSize;while(size>minSize){context.font=`${weight} ${size}px ${shareCanvasFont}`;if(context.measureText(text).width<=maxWidth)break;size-=2}return size}
function clipCanvasText(context,text,maxWidth){let output=String(text);if(context.measureText(output).width<=maxWidth)return output;while(output.length>1&&context.measureText(output+"…").width>maxWidth)output=output.slice(0,-1);return output+"…"}
function drawShareFrame(context,kind){const width=1200,height=630;context.clearRect(0,0,width,height);context.fillStyle="#fffdf8";context.fillRect(0,0,width,height);context.strokeStyle="#1f1c19";context.lineWidth=2;context.strokeRect(24,24,1152,582);context.fillStyle="#9b3344";context.fillRect(24,24,1152,14);context.fillRect(64,60,64,64);context.fillStyle="#fff";context.font=`900 24px ${shareCanvasFont}`;context.textAlign="center";context.textBaseline="middle";context.fillText("JP",96,92);context.textAlign="left";context.fillStyle="#1f1c19";context.font=`900 25px ${shareCanvasFont}`;context.fillText("JAPAN CHART PULSE",150,84);context.fillStyle="#9b3344";context.font=`800 17px ${shareCanvasFont}`;context.fillText(kind,150,114);context.textAlign="right";context.fillStyle="#70685f";context.font=`700 17px ${shareCanvasFont}`;context.fillText("LATEST  "+dashboard.latestDate,1136,88);context.strokeStyle="#d8cfc2";context.lineWidth=2;context.beginPath();context.moveTo(64,150);context.lineTo(1136,150);context.stroke();context.textAlign="left";context.textBaseline="alphabetic"}
function drawShareMetrics(context,stats){stats.forEach(([label,value],index)=>{const x=64+index*266;context.fillStyle="#f3eee4";context.fillRect(x,354,246,112);context.fillStyle="#9b3344";context.fillRect(x,354,246,6);context.fillStyle="#70685f";context.font=`800 17px ${shareCanvasFont}`;context.fillText(label,x+16,390);context.fillStyle="#1f1c19";context.font=`900 38px ${shareCanvasFont}`;context.fillText(value,x+16,442)})}
function drawArtistShareCard(a){const canvas=document.getElementById("shareCard"),context=canvas.getContext("2d");drawShareFrame(context,"ARTIST PROFILE");context.fillStyle="#70685f";context.font=`800 19px ${shareCanvasFont}`;context.fillText(scopeLabel()+"  /  "+dashboard.chartName,64,190);const artistSize=fitCanvasText(context,a.artist,790,72,40);context.fillStyle="#1f1c19";context.font=`900 ${artistSize}px ${shareCanvasFont}`;context.fillText(clipCanvasText(context,a.artist,790),64,292);context.textAlign="right";context.fillStyle="#9b3344";context.font=`800 16px ${shareCanvasFont}`;context.fillText("ARTIST RANK",1136,216);context.fillStyle="#1f1c19";context.font=`900 72px ${shareCanvasFont}`;context.fillText(a.rank?"#"+a.rank:"—",1136,292);context.textAlign="left";drawShareMetrics(context,[["延べ登場",a.appearances+"回"],["登場週",a.weeks+"週"],["Top 10",a.top10+"回"],["最高順位",a.best?"#"+a.best:"—"]]);context.fillStyle="#9b3344";context.font=`800 16px ${shareCanvasFont}`;context.fillText("TOP SONGS",64,510);context.fillStyle="#1f1c19";context.font=`700 20px ${shareCanvasFont}`;const songLine=(a.songs||[]).slice(0,3).map((song,index)=>(index+1)+". "+song.title).join("   /   ")||"ランクイン曲はありません";context.fillText(clipCanvasText(context,songLine,1072),64,544);context.fillStyle="#70685f";context.font=`700 16px ${shareCanvasFont}`;context.fillText(rankingYear()+"年集計  ・  "+dashboard.chartName,64,584)}
function drawSongShareCard(song){const canvas=document.getElementById("shareCard"),context=canvas.getContext("2d"),history=song.history||[],last=history.length?history[history.length-1]:null,latestRank=song.latestRank??(last&&last.date===dashboard.latestDate?last.rank:null);drawShareFrame(context,"SONG PROFILE");context.fillStyle="#70685f";context.font=`800 19px ${shareCanvasFont}`;context.fillText(scopeLabel()+"  /  "+dashboard.chartName,64,190);const titleSize=fitCanvasText(context,song.title,810,64,34);context.fillStyle="#1f1c19";context.font=`900 ${titleSize}px ${shareCanvasFont}`;context.fillText(clipCanvasText(context,song.title,810),64,278);context.fillStyle="#9b3344";context.font=`800 23px ${shareCanvasFont}`;context.fillText(clipCanvasText(context,song.artist,810),64,322);context.textAlign="right";context.fillStyle="#9b3344";context.font=`800 16px ${shareCanvasFont}`;context.fillText("HIT SONG RANK",1136,216);context.fillStyle="#1f1c19";context.font=`900 72px ${shareCanvasFont}`;context.fillText(song.rankingPosition?"#"+song.rankingPosition:"—",1136,292);context.textAlign="left";drawShareMetrics(context,[["最新順位",latestRank?"#"+latestRank:"—"],["最高順位",song.best?"#"+song.best:"—"],["登場週",(song.weeks??history.length)+"週"],["Top 10",(song.top10??history.filter(item=>item.rank<=10).length)+"回"]]);context.fillStyle="#9b3344";context.font=`800 16px ${shareCanvasFont}`;context.fillText("CHART HISTORY",64,510);context.fillStyle="#1f1c19";context.font=`700 21px ${shareCanvasFont}`;const first=history[0],period=first&&last?first.date+"  —  "+last.date:"順位履歴なし";context.fillText(period,64,544);context.fillStyle="#70685f";context.font=`700 16px ${shareCanvasFont}`;context.fillText(rankingYear()+"年集計  ・  "+dashboard.chartName,64,584)}
function canvasBlob(){return new Promise((resolve,reject)=>document.getElementById("shareCard").toBlob(blob=>blob?resolve(blob):reject(new Error("画像を作成できませんでした")),"image/png"))}
async function copyText(value){if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(value);return}const field=document.createElement("textarea");field.value=value;field.style.position="fixed";field.style.opacity="0";document.body.appendChild(field);field.select();const copied=document.execCommand("copy");field.remove();if(!copied)throw new Error("コピーできませんでした")}
function openShareDialog(){if(!currentArtistName)return;const artist=artistDetails.find(item=>item.artist===currentArtistName);if(!artist)return;currentShareTarget={type:"artist",data:artist};document.getElementById("shareKind").textContent="SHARE ARTIST";document.getElementById("shareTitle").textContent=artist.artist+"を共有";setShareStatus("");drawArtistShareCard(artist);const dialog=document.getElementById("shareDialog");if(!dialog.open)dialog.showModal()}
function openSongShareDialog(){if(!currentSongShare)return;const ranked=rankedSongsForYear().find(item=>item.artist===currentSongShare.artist&&item.title===currentSongShare.title),song={...currentSongShare,...(ranked||{})};currentShareTarget={type:"song",data:song};document.getElementById("shareKind").textContent="SHARE SONG";document.getElementById("shareTitle").textContent=song.title+"を共有";setShareStatus("");drawSongShareCard(song);const dialog=document.getElementById("shareDialog");if(!dialog.open)dialog.showModal()}
function sharePayload(){if(!currentShareTarget)return null;if(currentShareTarget.type==="song"){const song=currentShareTarget.data;return{url:songShareUrl(song.artist,song.title),text:song.artist+"「"+song.title+"」のBillboard JAPANチャート推移をチェック",title:song.title+" / "+song.artist+" | JAPAN CHART PULSE",fileName:"chart-pulse-song.png"}}const artist=currentShareTarget.data;return{url:artistShareUrl(artist.artist),text:artist.artist+"のBillboard JAPANチャート推移をチェック",title:artist.artist+" | JAPAN CHART PULSE",fileName:"chart-pulse-artist.png"}}
document.getElementById("openShare").addEventListener("click",openShareDialog);document.getElementById("openSongShare").addEventListener("click",openSongShareDialog);const shareDialog=document.getElementById("shareDialog");document.getElementById("shareClose").addEventListener("click",()=>shareDialog.close());shareDialog.addEventListener("click",event=>{if(event.target===event.currentTarget)event.currentTarget.close()});
document.getElementById("copyShareLink").addEventListener("click",async()=>{const payload=sharePayload();if(!payload)return;try{await copyText(payload.url);setShareStatus("リンクをコピーしました。","success")}catch(error){setShareStatus("リンクをコピーできませんでした。","error")}});
document.getElementById("shareWithImage").addEventListener("click",async()=>{const payload=sharePayload();if(!payload)return;setShareStatus("共有画像を準備しています…");try{const blob=await canvasBlob(),file=new File([blob],payload.fileName,{type:"image/png"}),shareData={title:payload.title,text:payload.text,url:payload.url,files:[file]};if(navigator.share&&navigator.canShare?.({files:[file]})){await navigator.share(shareData);setShareStatus("画像とリンクを共有しました。","success");return}const popup=window.open("about:blank","_blank","width=640,height=520");if(popup)popup.opener=null;let imageReady=false;if(navigator.clipboard?.write&&window.ClipboardItem){try{await navigator.clipboard.write([new ClipboardItem({"image/png":blob})]);imageReady=true}catch(error){imageReady=false}}if(!imageReady){const download=document.createElement("a");download.href=URL.createObjectURL(blob);download.download=payload.fileName;download.click();setTimeout(()=>URL.revokeObjectURL(download.href),1000)}const query=new URLSearchParams({text:payload.text,url:payload.url}),composer="https://twitter.com/intent/tweet?"+query.toString();if(popup)popup.location.href=composer;else window.open(composer,"_blank","noopener,noreferrer");setShareStatus(imageReady?"画像をコピーしました。Xの投稿画面で貼り付けてください。":"画像を保存しました。Xの投稿画面で添付してください。","success")}catch(error){if(error?.name==="AbortError"){setShareStatus("共有をキャンセルしました。");return}setShareStatus("画像付き共有を開始できませんでした。","error")}});const applyDashboardWithScopeLabel=applyDashboard;applyDashboard=()=>{artistExpanded=false;songDisplayLimit=5;applyDashboardWithScopeLabel();document.getElementById("scopeName").textContent=scopeLabel()};
function emptyArtistDetail(name){const zeroes=()=>Array(53).fill(0);return{artist:name,appearances:0,weeks:0,songsCount:0,top10:0,best:null,active:false,previousYtd:0,ytdChange:0,rank:null,weeklyCumulative:{"2024":zeroes(),"2025":zeroes(),"2026":zeroes()},yearCounts:{"2024":0,"2025":0,"2026":0},songs:[]}}function artistDetailForChart(name,code=chartCode){return dashboards[scopeCode]?.[code]?.artistDetails?.find(item=>item.artist===name)||emptyArtistDetail(name)}function renderArtistDetailAcrossCharts(name,updateUrl=true){if(!name)return;const a=artistDetailForChart(name);currentArtistName=name;if(updateUrl){const base=location.href.split("#")[0];history.replaceState(null,"",base);history.pushState({modal:"artist",artist:name,scope:scopeCode,chart:chartCode},"",artistShareUrl(name));artistHistoryActive=true}document.getElementById("detailName").textContent=name;document.querySelectorAll("[data-detail-chart]").forEach(button=>{const active=button.dataset.detailChart===chartCode;button.classList.toggle("active",active);button.setAttribute("aria-selected",String(active))});document.getElementById("detailChartContext").textContent=dashboard.chartName+(a.appearances?" の集計":" ではランクイン実績がありません");const stats=[["延べ登場",a.appearances+"回"],["登場週",a.weeks+"週"],["ランクイン曲",a.songsCount+"曲"],["Top 10",a.top10+"回"],["最高順位",a.best?"#"+a.best:"—"],["前年同期比",signed(a.ytdChange)]];document.getElementById("detailStats").innerHTML=stats.map(([label,value])=>`<div class="detail-stat"><span>${label}</span><strong>${value}</strong></div>`).join("");document.getElementById("detailSongs").innerHTML=a.songs.length?a.songs.map(song=>`<button class="song-item" type="button" data-song-title="${esc(song.title)}" data-song-artist="${esc(name)}"><div class="song-title">${esc(song.title)}</div><div class="song-meta">延べ${song.appearances}回・${song.weeks}週・最高#${song.best}・最終登場 ${song.latest}</div></button>`).join(""):`<p class="muted">${esc(dashboard.chartName)}では2026年のランクイン曲はありません。</p>`;const dialog=document.getElementById("detailDialog");if(!dialog.open)dialog.showModal();requestAnimationFrame(()=>drawYearTrend(a))}openDetail=renderArtistDetailAcrossCharts;document.getElementById("detailChartSwitch").addEventListener("click",event=>{const button=event.target.closest("[data-detail-chart]");if(!button||!currentArtistName||button.dataset.detailChart===chartCode)return;const name=currentArtistName;chartCode=button.dataset.detailChart;applyDashboard();history.replaceState({modal:"artist",artist:name,scope:scopeCode,chart:chartCode},"",artistShareUrl(name));openDetail(name,false)});document.getElementById("globalSearch").addEventListener("input",renderGlobalSearch);document.addEventListener("click",event=>{const target=event.target.closest("[data-search-chart]");if(!target)return;event.preventDefault();event.stopImmediatePropagation();const nextChart=target.dataset.searchChart,artist=target.dataset.songArtist||target.dataset.artist,title=target.dataset.songTitle;if(nextChart&&nextChart!==chartCode){chartCode=nextChart;applyDashboard()}if(title)openSongDetail(artist,title);else if(artist)openDetail(artist)},true);document.getElementById("openShare").addEventListener("click",event=>{if(!currentArtistName)return;event.preventDefault();event.stopImmediatePropagation();const artist=artistDetailForChart(currentArtistName);currentShareTarget={type:"artist",data:artist};document.getElementById("shareKind").textContent="SHARE ARTIST";document.getElementById("shareTitle").textContent=artist.artist+"を共有";setShareStatus("");drawArtistShareCard(artist);const dialog=document.getElementById("shareDialog");if(!dialog.open)dialog.showModal()},true);const applyDashboardWithGlobalSearch=applyDashboard;applyDashboard=()=>{applyDashboardWithGlobalSearch();renderGlobalSearch()};
function scopeCodeLabel(code){return({boys:"ボーイズグループ",girls:"ガールズグループ",korean:"K-POPグループ",all:"全アーティスト"}[code]||code)}globalSearchData=()=>{const artistMap=new Map(),songMap=new Map();Object.entries(dashboards).forEach(([sourceScope,charts])=>{chartOrder.forEach(sourceChart=>{const details=charts?.[sourceChart]?.artistDetails||[];details.forEach(artist=>{if(!artist?.artist)return;let artistEntry=artistMap.get(artist.artist);if(!artistEntry){artistEntry={artist:artist.artist,sources:new Set};artistMap.set(artist.artist,artistEntry)}artistEntry.sources.add(sourceScope+"|"+sourceChart);(artist.songs||[]).forEach(song=>{if(!song?.title)return;const key=artist.artist+"\u0000"+song.title;let songEntry=songMap.get(key);if(!songEntry){songEntry={artist:artist.artist,title:song.title,sources:new Set};songMap.set(key,songEntry)}songEntry.sources.add(sourceScope+"|"+sourceChart)})})})});return{artists:[...artistMap.values()],songs:[...songMap.values()]}};function preferredSearchSource(sources){const parsed=[...sources].map(value=>{const[scope,chart]=value.split("|");return{scope,chart}});return parsed.find(item=>item.scope===scopeCode&&item.chart===chartCode)||parsed.find(item=>item.scope==="all"&&item.chart===chartCode)||parsed.find(item=>item.chart===chartCode)||parsed.find(item=>item.scope===scopeCode)||parsed[0]||{scope:scopeCode,chart:chartCode}}function searchSourceSummary(sources){const parsed=[...sources].map(value=>{const[scope,chart]=value.split("|");return{scope,chart}}),scopes=[...new Set(parsed.map(item=>scopeCodeLabel(item.scope)))],charts=[...new Set(parsed.map(item=>chartLabel(item.chart)))];return(scopes.slice(0,2).join(" / ")+(scopes.length>2?" ほか":""))+" ・ "+charts.join(" / ")}renderGlobalSearch=()=>{const input=document.getElementById("globalSearch"),results=document.getElementById("searchResults"),status=document.getElementById("searchStatus"),query=normalized(input.value).trim();if(!query){results.innerHTML="";status.textContent="文字を入力すると候補を表示します。";return}const index=globalSearchData(),matchedArtists=index.artists.filter(item=>normalized(item.artist).includes(query)).sort((a,b)=>resultPriority(a.artist,query)-resultPriority(b.artist,query)||a.artist.localeCompare(b.artist,"ja")),matchedSongs=index.songs.filter(item=>normalized(item.title+" "+item.artist).includes(query)).sort((a,b)=>resultPriority(a.title,query)-resultPriority(b.title,query)||a.title.localeCompare(b.title,"ja")),visibleArtists=matchedArtists.slice(0,12),visibleSongs=matchedSongs.slice(0,18);status.textContent=`全表示対象からアーティスト ${matchedArtists.length}組・楽曲 ${matchedSongs.length}曲が見つかりました${matchedArtists.length>12||matchedSongs.length>18?"（関連度の高い候補を表示）":""}`;results.innerHTML=visibleArtists.map(item=>{const source=preferredSearchSource(item.sources);return`<button class="search-result" type="button" data-global-scope="${source.scope}" data-global-chart="${source.chart}" data-artist="${esc(item.artist)}"><span class="search-result-main"><span class="search-result-name">${esc(item.artist)}</span><span class="search-result-sub">${esc(searchSourceSummary(item.sources))}</span></span><span class="search-result-type">ARTIST</span></button>`}).join("")+visibleSongs.map(item=>{const source=preferredSearchSource(item.sources);return`<button class="search-result" type="button" data-global-scope="${source.scope}" data-global-chart="${source.chart}" data-song-title="${esc(item.title)}" data-song-artist="${esc(item.artist)}"><span class="search-result-main"><span class="search-result-name">${esc(item.title)}</span><span class="search-result-sub">${esc(item.artist)} ・ ${esc(searchSourceSummary(item.sources))}</span></span><span class="search-result-type">SONG</span></button>`}).join("");if(!results.innerHTML)results.innerHTML='<p class="search-status">一致するデータはありません。</p>'};document.getElementById("globalSearch").addEventListener("input",renderGlobalSearch);document.addEventListener("click",event=>{const target=event.target.closest("[data-global-chart]");if(!target)return;event.preventDefault();event.stopImmediatePropagation();const nextScope=target.dataset.globalScope,nextChart=target.dataset.globalChart,artist=target.dataset.songArtist||target.dataset.artist,title=target.dataset.songTitle;if(nextScope&&nextChart&&(nextScope!==scopeCode||nextChart!==chartCode)){scopeCode=nextScope;chartCode=nextChart;applyDashboard()}if(title)openSongDetail(artist,title);else if(artist)openDetail(artist)},true);
const shareAcid="#b8ff25",shareAccent="#4f7200";let artistShareChartCode=chartCode;drawShareFrame=(context,kind)=>{const width=1200,height=630;context.clearRect(0,0,width,height);context.fillStyle="#fffdf8";context.fillRect(0,0,width,height);context.strokeStyle="#1f1c19";context.lineWidth=2;context.strokeRect(24,24,1152,582);context.fillStyle=shareAcid;context.fillRect(24,24,1152,14);context.fillRect(64,60,64,64);context.fillStyle="#111";context.font=`900 24px ${shareCanvasFont}`;context.textAlign="center";context.textBaseline="middle";context.fillText("JP",96,92);context.textAlign="left";context.fillStyle="#1f1c19";context.font=`900 25px ${shareCanvasFont}`;context.fillText("JAPAN CHART PULSE",150,84);context.fillStyle=shareAccent;context.font=`800 17px ${shareCanvasFont}`;context.fillText(kind,150,114);context.textAlign="right";context.fillStyle="#70685f";context.font=`700 17px ${shareCanvasFont}`;context.fillText("LATEST  "+dashboard.latestDate,1136,88);context.strokeStyle="#d8cfc2";context.lineWidth=2;context.beginPath();context.moveTo(64,150);context.lineTo(1136,150);context.stroke();context.textAlign="left";context.textBaseline="alphabetic"};drawShareMetrics=(context,stats)=>{stats.forEach(([label,value],index)=>{const x=64+index*266;context.fillStyle="#f3eee4";context.fillRect(x,354,246,112);context.fillStyle=shareAcid;context.fillRect(x,354,246,6);context.fillStyle="#70685f";context.font=`800 17px ${shareCanvasFont}`;context.fillText(label,x+16,390);context.fillStyle="#1f1c19";context.font=`900 38px ${shareCanvasFont}`;context.fillText(value,x+16,442)})};function drawMiniChartFrame(context,title){const x=824,y=178,width=312,height=148;context.fillStyle="#f3eee4";context.fillRect(x,y,width,height);context.fillStyle=shareAccent;context.font=`800 14px ${shareCanvasFont}`;context.fillText(title,x+14,y+24);context.strokeStyle="#d8cfc2";context.lineWidth=1;[0,1,2].forEach(index=>{const lineY=y+48+index*38;context.beginPath();context.moveTo(x+14,lineY);context.lineTo(x+width-14,lineY);context.stroke()});return{x:x+14,y:y+42,width:width-28,height:height-54}}function drawArtistMiniChart(context,artist){const area=drawMiniChartFrame(context,"2026 CUMULATIVE"),values=artist.weeklyCumulative?.["2026"]||[],maximum=Math.max(...values,1);context.strokeStyle="#111";context.lineWidth=4;context.lineJoin="round";context.lineCap="round";context.beginPath();values.forEach((value,index)=>{const x=area.x+(values.length<=1?0:index/(values.length-1))*area.width,y=area.y+area.height-(value/maximum)*area.height;if(index===0)context.moveTo(x,y);else context.lineTo(x,y)});context.stroke();context.fillStyle=shareAcid;const last=values.length-1,lastX=area.x+area.width,lastY=area.y+area.height-((values[last]||0)/maximum)*area.height;context.beginPath();context.arc(lastX,lastY,7,0,Math.PI*2);context.fill();context.strokeStyle="#111";context.lineWidth=2;context.stroke();context.fillStyle="#111";context.font=`900 18px ${shareCanvasFont}`;context.textAlign="right";context.fillText((values[last]||0)+"回",area.x+area.width,area.y+18);context.textAlign="left"}function drawSongMiniChart(context,song){const area=drawMiniChartFrame(context,"WEEKLY RANK"),history=[...(song.history||[])].sort((a,b)=>a.date.localeCompare(b.date));if(!history.length){context.fillStyle="#70685f";context.font=`700 16px ${shareCanvasFont}`;context.fillText("順位推移データなし",area.x,area.y+48);return}context.strokeStyle="#111";context.lineWidth=4;context.lineJoin="round";context.lineCap="round";context.beginPath();history.forEach((item,index)=>{const x=area.x+(history.length<=1?.5:index/(history.length-1))*area.width,y=area.y+((Math.max(1,Math.min(100,item.rank))-1)/99)*area.height;if(index===0)context.moveTo(x,y);else context.lineTo(x,y)});context.stroke();const last=history[history.length-1],lastY=area.y+((Math.max(1,Math.min(100,last.rank))-1)/99)*area.height;context.fillStyle=shareAcid;context.beginPath();context.arc(area.x+area.width,lastY,7,0,Math.PI*2);context.fill();context.strokeStyle="#111";context.lineWidth=2;context.stroke();context.fillStyle="#111";context.font=`900 18px ${shareCanvasFont}`;context.textAlign="right";context.fillText("#"+last.rank,area.x+area.width,area.y+18);context.textAlign="left"}drawArtistShareCard=artist=>{const dialog=document.getElementById("shareDialog");if(!dialog.open)artistShareChartCode=chartCode;const selected=artistDetailForChart(artist.artist,artistShareChartCode),selectedDashboard=dashboards[scopeCode][artistShareChartCode];currentShareTarget={type:"artist",data:selected};const picker=document.getElementById("shareChartPicker");picker.hidden=false;picker.querySelectorAll("[data-share-chart]").forEach(button=>button.classList.toggle("active",button.dataset.shareChart===artistShareChartCode));document.getElementById("shareTitle").textContent=selected.artist+"を共有・"+chartLabel(artistShareChartCode);const canvas=document.getElementById("shareCard"),context=canvas.getContext("2d");drawShareFrame(context,"ARTIST PROFILE");context.fillStyle="#70685f";context.font=`800 19px ${shareCanvasFont}`;context.fillText(scopeLabel()+"  /  "+selectedDashboard.chartName,64,190);const artistSize=fitCanvasText(context,selected.artist,720,68,38);context.fillStyle="#1f1c19";context.font=`900 ${artistSize}px ${shareCanvasFont}`;context.fillText(clipCanvasText(context,selected.artist,720),64,292);drawArtistMiniChart(context,selected);drawShareMetrics(context,[["延べ登場",selected.appearances+"回"],["登場週",selected.weeks+"週"],["Top 10",selected.top10+"回"],["最高順位",selected.best?"#"+selected.best:"—"]]);context.fillStyle=shareAccent;context.font=`800 16px ${shareCanvasFont}`;context.fillText("TOP SONGS",64,510);context.fillStyle="#1f1c19";context.font=`700 20px ${shareCanvasFont}`;const songLine=(selected.songs||[]).slice(0,3).map((song,index)=>(index+1)+". "+song.title).join("   /   ")||"ランクイン曲はありません";context.fillText(clipCanvasText(context,songLine,1072),64,544);context.fillStyle="#70685f";context.font=`700 16px ${shareCanvasFont}`;context.fillText(rankingYear()+"年集計  ・  "+selectedDashboard.chartName,64,584)};drawSongShareCard=song=>{document.getElementById("shareChartPicker").hidden=true;const canvas=document.getElementById("shareCard"),context=canvas.getContext("2d"),history=song.history||[],last=history.length?history[history.length-1]:null,latestRank=song.latestRank??(last&&last.date===dashboard.latestDate?last.rank:null);drawShareFrame(context,"SONG PROFILE");context.fillStyle="#70685f";context.font=`800 19px ${shareCanvasFont}`;context.fillText(scopeLabel()+"  /  "+dashboard.chartName,64,190);const titleSize=fitCanvasText(context,song.title,720,60,32);context.fillStyle="#1f1c19";context.font=`900 ${titleSize}px ${shareCanvasFont}`;context.fillText(clipCanvasText(context,song.title,720),64,270);context.fillStyle=shareAccent;context.font=`800 23px ${shareCanvasFont}`;context.fillText(clipCanvasText(context,song.artist,720),64,316);drawSongMiniChart(context,song);drawShareMetrics(context,[["最新順位",latestRank?"#"+latestRank:"—"],["最高順位",song.best?"#"+song.best:"—"],["登場週",(song.weeks??history.length)+"週"],["Top 10",(song.top10??history.filter(item=>item.rank<=10).length)+"回"]]);context.fillStyle=shareAccent;context.font=`800 16px ${shareCanvasFont}`;context.fillText("CHART HISTORY",64,510);context.fillStyle="#1f1c19";context.font=`700 21px ${shareCanvasFont}`;const first=history[0],period=first&&last?first.date+"  —  "+last.date:"順位履歴なし";context.fillText(period,64,544);context.fillStyle="#70685f";context.font=`700 16px ${shareCanvasFont}`;context.fillText(rankingYear()+"年集計  ・  "+dashboard.chartName,64,584)};document.getElementById("shareChartPicker").addEventListener("click",event=>{const button=event.target.closest("[data-share-chart]");if(!button||currentShareTarget?.type!=="artist")return;artistShareChartCode=button.dataset.shareChart;drawArtistShareCard(currentShareTarget.data)});const sharePayloadBeforeChartSelection=sharePayload;sharePayload=()=>{if(currentShareTarget?.type!=="artist")return sharePayloadBeforeChartSelection();const artist=currentShareTarget.data,base=location.href.split("#")[0],params=new URLSearchParams({artist:artist.artist,scope:scopeCode,chart:artistShareChartCode});return{url:base+"#"+params.toString(),text:artist.artist+"のBillboard JAPANチャート推移をチェック",title:artist.artist+" | JAPAN CHART PULSE",fileName:"chart-pulse-artist.png"}};
let shareViewMode="summary";const latestMobileViewport=matchMedia("(max-width:650px)"),latestAutoIsPausedWithInteraction=latestAutoIsPaused;latestAutoIsPaused=()=>latestMobileViewport.matches||latestAutoIsPausedWithInteraction();function syncShareViewPicker(){document.querySelectorAll("[data-share-view]").forEach(button=>button.classList.toggle("active",button.dataset.shareView===shareViewMode))}function drawArtistShareSummary(context,selected,selectedDashboard){context.fillStyle="#70685f";context.font=`800 19px ${shareCanvasFont}`;context.fillText(scopeLabel()+"  /  "+selectedDashboard.chartName,64,190);const artistSize=fitCanvasText(context,selected.artist,1072,72,40);context.fillStyle="#1f1c19";context.font=`900 ${artistSize}px ${shareCanvasFont}`;context.fillText(clipCanvasText(context,selected.artist,1072),64,292);drawShareMetrics(context,[["延べ登場",selected.appearances+"回"],["登場週",selected.weeks+"週"],["Top 10",selected.top10+"回"],["最高順位",selected.best?"#"+selected.best:"—"]]);context.fillStyle=shareAccent;context.font=`800 16px ${shareCanvasFont}`;context.fillText("TOP SONGS",64,510);context.fillStyle="#1f1c19";context.font=`700 20px ${shareCanvasFont}`;const songLine=(selected.songs||[]).slice(0,3).map((song,index)=>(index+1)+". "+song.title).join("   /   ")||"ランクイン曲はありません";context.fillText(clipCanvasText(context,songLine,1072),64,544);context.fillStyle="#70685f";context.font=`700 16px ${shareCanvasFont}`;context.fillText(rankingYear()+"年集計  ・  "+selectedDashboard.chartName,64,584)}function drawSongShareSummary(context,song){const history=song.history||[],last=history.length?history[history.length-1]:null,latestRank=song.latestRank??(last&&last.date===dashboard.latestDate?last.rank:null);context.fillStyle="#70685f";context.font=`800 19px ${shareCanvasFont}`;context.fillText(scopeLabel()+"  /  "+dashboard.chartName,64,190);const titleSize=fitCanvasText(context,song.title,1072,62,34);context.fillStyle="#1f1c19";context.font=`900 ${titleSize}px ${shareCanvasFont}`;context.fillText(clipCanvasText(context,song.title,1072),64,270);context.fillStyle=shareAccent;context.font=`800 23px ${shareCanvasFont}`;context.fillText(clipCanvasText(context,song.artist,1072),64,316);drawShareMetrics(context,[["最新順位",latestRank?"#"+latestRank:"—"],["最高順位",song.best?"#"+song.best:"—"],["登場週",(song.weeks??history.length)+"週"],["Top 10",(song.top10??history.filter(item=>item.rank<=10).length)+"回"]]);context.fillStyle=shareAccent;context.font=`800 16px ${shareCanvasFont}`;context.fillText("CHART HISTORY",64,510);context.fillStyle="#1f1c19";context.font=`700 21px ${shareCanvasFont}`;const first=history[0],period=first&&last?first.date+"  —  "+last.date:"順位履歴なし";context.fillText(period,64,544);context.fillStyle="#70685f";context.font=`700 16px ${shareCanvasFont}`;context.fillText(rankingYear()+"年集計  ・  "+dashboard.chartName,64,584)}function graphArea(context,title,subtitle){context.fillStyle="#70685f";context.font=`800 17px ${shareCanvasFont}`;context.fillText(subtitle,64,184);context.fillStyle="#1f1c19";context.font=`900 38px ${shareCanvasFont}`;context.fillText(clipCanvasText(context,title,1072),64,230);return{x:90,y:272,width:1026,height:242}}function drawArtistGraphShare(context,artist,selectedDashboard){const area=graphArea(context,artist.artist,scopeLabel()+"  /  "+selectedDashboard.chartName+"  /  2024—2026 累積推移"),years=["2024","2025","2026"],colors={"2024":"#6b7280","2025":"#0072b2","2026":"#d55e00"},series=years.map(year=>({year,values:artist.weeklyCumulative?.[year]||[]})),maximum=Math.max(1,...series.flatMap(item=>item.values)),axisMaximum=Math.max(10,Math.ceil(maximum/10)*10);context.fillStyle="#f3eee4";context.fillRect(area.x,area.y,area.width,area.height);context.strokeStyle="#d8cfc2";context.lineWidth=1;context.font=`700 14px ${shareCanvasFont}`;context.fillStyle="#70685f";context.textAlign="right";for(let index=0;index<=4;index++){const y=area.y+area.height*index/4,value=Math.round(axisMaximum*(1-index/4));context.beginPath();context.moveTo(area.x,y);context.lineTo(area.x+area.width,y);context.stroke();context.fillText(String(value),area.x-12,y+5)}context.textAlign="center";[1,13,26,39,53].forEach(week=>{const x=area.x+(week-1)/52*area.width;context.fillText("W"+week,x,area.y+area.height+24)});series.forEach(({year,values})=>{if(!values.length)return;context.strokeStyle=colors[year];context.lineWidth=5;context.lineJoin="round";context.lineCap="round";context.beginPath();values.forEach((value,index)=>{const x=area.x+(values.length<=1?0:index/(Math.max(52,values.length-1)))*area.width,y=area.y+area.height-value/axisMaximum*area.height;if(index===0)context.moveTo(x,y);else context.lineTo(x,y)});context.stroke()});context.textAlign="left";years.forEach((year,index)=>{const x=760+index*126,y=560;context.fillStyle=colors[year];context.fillRect(x,y-12,30,5);context.fillStyle="#1f1c19";context.font=`800 16px ${shareCanvasFont}`;context.fillText(year,x+40,y-5)});context.fillStyle="#70685f";context.font=`700 15px ${shareCanvasFont}`;context.fillText("詳細画面の年別累積チャートを共有用に再構成",64,584)}function drawSongGraphShare(context,song){const history=[...(song.history||[])].sort((a,b)=>a.date.localeCompare(b.date)),area=graphArea(context,song.title,song.artist+"  /  "+dashboard.chartName+"  /  週間順位推移");context.fillStyle="#f3eee4";context.fillRect(area.x,area.y,area.width,area.height);const rankY=rank=>area.y+(Math.max(1,Math.min(100,rank))-1)/99*area.height;context.fillStyle="rgba(184,255,37,.2)";context.fillRect(area.x,area.y,area.width,rankY(10)-area.y);context.strokeStyle="#d8cfc2";context.lineWidth=1;context.font=`700 14px ${shareCanvasFont}`;context.fillStyle="#70685f";context.textAlign="right";[1,10,25,50,75,100].forEach(rank=>{const y=rankY(rank);context.beginPath();context.moveTo(area.x,y);context.lineTo(area.x+area.width,y);context.stroke();context.fillText("#"+rank,area.x-12,y+5)});if(history.length){const dates=history.map(item=>new Date(item.date+"T00:00:00").getTime()),minimum=Math.min(...dates),maximum=Math.max(...dates),span=Math.max(1,maximum-minimum),pointX=index=>area.x+(history.length<=1?.5:(dates[index]-minimum)/span)*area.width;context.strokeStyle="#0072b2";context.lineWidth=5;context.lineJoin="round";context.lineCap="round";context.beginPath();history.forEach((item,index)=>{const x=pointX(index),y=rankY(item.rank),gap=index?dates[index]-dates[index-1]:0;if(index===0||gap>9*86400000)context.moveTo(x,y);else context.lineTo(x,y)});context.stroke();history.forEach((item,index)=>{context.fillStyle=item.rank<=10?shareAcid:"#79dcff";context.beginPath();context.arc(pointX(index),rankY(item.rank),6,0,Math.PI*2);context.fill();context.strokeStyle="#1f1c19";context.lineWidth=1.5;context.stroke()});context.textAlign="left";context.fillStyle="#70685f";context.font=`700 15px ${shareCanvasFont}`;context.fillText(history[0].date,area.x,area.y+area.height+24);context.textAlign="right";context.fillText(history[history.length-1].date,area.x+area.width,area.y+area.height+24)}else{context.textAlign="center";context.fillStyle="#70685f";context.font=`800 20px ${shareCanvasFont}`;context.fillText("順位推移データなし",area.x+area.width/2,area.y+area.height/2)}context.textAlign="left";context.fillStyle="#70685f";context.font=`700 15px ${shareCanvasFont}`;context.fillText("詳細画面の週間順位チャートを共有用に再構成",64,584)}drawArtistShareCard=artist=>{const dialog=document.getElementById("shareDialog");if(!dialog.open){artistShareChartCode=chartCode;shareViewMode="summary"}const selected=artistDetailForChart(artist.artist,artistShareChartCode),selectedDashboard=dashboards[scopeCode][artistShareChartCode];currentShareTarget={type:"artist",data:selected};syncShareViewPicker();const picker=document.getElementById("shareChartPicker");picker.hidden=false;picker.querySelectorAll("[data-share-chart]").forEach(button=>button.classList.toggle("active",button.dataset.shareChart===artistShareChartCode));document.getElementById("shareTitle").textContent=selected.artist+"を共有・"+chartLabel(artistShareChartCode);const context=document.getElementById("shareCard").getContext("2d");drawShareFrame(context,shareViewMode==="graph"?"ARTIST GRAPH":"ARTIST PROFILE");if(shareViewMode==="graph")drawArtistGraphShare(context,selected,selectedDashboard);else drawArtistShareSummary(context,selected,selectedDashboard)};drawSongShareCard=song=>{const dialog=document.getElementById("shareDialog");if(!dialog.open)shareViewMode="summary";currentShareTarget={type:"song",data:song};syncShareViewPicker();document.getElementById("shareChartPicker").hidden=true;document.getElementById("shareTitle").textContent=song.title+"を共有";const context=document.getElementById("shareCard").getContext("2d");drawShareFrame(context,shareViewMode==="graph"?"SONG GRAPH":"SONG PROFILE");if(shareViewMode==="graph")drawSongGraphShare(context,song);else drawSongShareSummary(context,song)};document.getElementById("shareViewPicker").addEventListener("click",event=>{const button=event.target.closest("[data-share-view]");if(!button||button.dataset.shareView===shareViewMode)return;shareViewMode=button.dataset.shareView;if(currentShareTarget?.type==="artist")drawArtistShareCard(currentShareTarget.data);else if(currentShareTarget?.type==="song")drawSongShareCard(currentShareTarget.data)});
function switchChart(code){chartCode=code;applyDashboard()}
function switchScope(code){scopeCode=code;applyDashboard()}
initLatestCarousel();document.querySelectorAll("[data-chart]").forEach(button=>button.addEventListener("click",()=>switchChart(button.dataset.chart)));document.querySelectorAll("[data-scope]").forEach(button=>button.addEventListener("click",()=>switchScope(button.dataset.scope)));const sharedState=new URLSearchParams(location.hash.slice(1)),initialScope=sharedState.get("scope"),initialChart=sharedState.get("chart"),initialArtist=sharedState.get("artist"),initialSong=sharedState.get("song"),initialSongArtist=sharedState.get("songArtist");if(dashboards[initialScope]?.[initialChart]){scopeCode=initialScope;chartCode=initialChart}applyDashboard();if(initialSong&&initialSongArtist)openSongDetail(initialSongArtist,initialSong,false);else if(initialArtist)openDetail(initialArtist,false);
</script>
</body></html>
"""


def save_site(matched_by_chart, collections_by_chart):
    overall_entries_by_chart = {}
    for chart_code, chart_collections in collections_by_chart.items():
        overall_entries = []
        for collection in chart_collections:
            for entry in collection["entries"]:
                item = dict(entry)
                item["year"] = collection["year"]
                item["target_artist"] = entry["artist"]
                overall_entries.append(item)
        overall_entries_by_chart[chart_code] = overall_entries

    def entries_for_aliases(alias_map):
        alias_lookup = {
            normalize_artist_name(alias): artist
            for artist, aliases in alias_map.items()
            for alias in aliases
        }
        scoped_entries_by_chart = {}
        for chart_code, entries in overall_entries_by_chart.items():
            scoped_entries = []
            for entry in entries:
                target_artist = alias_lookup.get(
                    normalize_artist_name(entry["artist"])
                )
                if target_artist is None:
                    continue
                item = dict(entry)
                item["target_artist"] = target_artist
                scoped_entries.append(item)
            scoped_entries_by_chart[chart_code] = scoped_entries
        return scoped_entries_by_chart

    girls_entries_by_chart = entries_for_aliases(GIRLS_GROUP_ALIASES)
    korean_entries_by_chart = entries_for_aliases(KOREAN_IDOL_ALIASES)

    scope_sources = {
        "boys": (matched_by_chart, TARGET_ARTISTS),
        "girls": (girls_entries_by_chart, GIRLS_GROUP_ARTISTS),
        "korean": (korean_entries_by_chart, KOREAN_IDOL_ARTISTS),
        "all": (overall_entries_by_chart, None),
    }
    dashboards = {
        scope: {
            chart_code: build_dashboard_data(
                entries_by_chart[chart_code],
                collections_by_chart[chart_code],
                chart_code,
                artist_names,
            )
            for chart_code in CHART_CODES
        }
        for scope, (entries_by_chart, artist_names) in scope_sources.items()
    }
    dashboard_json = json.dumps(
        dashboards,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    hot_dashboard = dashboards["boys"][CHART_CODE]
    replacements = {
        "__DASHBOARD_DATA__": dashboard_json,
        "__LATEST_DATE__": hot_dashboard["latestDate"],
        "__GENERATED_AT__": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    document = HTML_TEMPLATE
    for placeholder, value in replacements.items():
        replacement = value if placeholder == "__DASHBOARD_DATA__" else html.escape(value)
        document = document.replace(placeholder, replacement)
    encoded_document = document.encode("utf-8")
    SITE_FILE.write_bytes(encoded_document)
    PREVIEW_FILE.write_bytes(encoded_document)

# ============================================================
# ターミナル表示
# ============================================================

def terminal_number(value):
    return "-" if value == 0 else str(value)


def print_results(results):
    print()
    print("=" * 98)
    print("2026年のランクイン回数順")
    print("=" * 98)

    print(
        f"{'順位':>4}  "
        f"{'アーティスト':<42} "
        f"{'2024':>7} "
        f"{'2025':>7} "
        f"{'2026':>7} "
        f"{'25→26':>8}"
    )

    print("-" * 98)

    for result in results:
        print(
            f"{result['rank_2026']:>4}  "
            f"{result['artist']:<42} "
            f"{terminal_number(result['count_2024']):>7} "
            f"{terminal_number(result['count_2025']):>7} "
            f"{terminal_number(result['count_2026']):>7} "
            f"{result['change_2026_vs_2025']:>8}"
        )


# ============================================================
# メイン
# ============================================================

def main():
    create_directories()

    print(
        f"{CHART_NAMES[CHART_CODE]}の"
        "2017〜2026年を収集します。"
    )

    print()
    print("2017〜2025年：各年の全公開週")
    print(
        "2026年：実行日以前の"
        "最新水曜日まで"
    )
    print("2017〜2023年は収集・保存のみで、現在の分析には使用しません。")
    print()
    print(
        "Chromeを開かず、公式ページから"
        "HTMLを直接取得します。"
    )

    opener = None
    collections_by_chart = {}

    for chart_code in CHART_CODES:
        chart_collections = []
        print()
        print("#" * 72)
        print(CHART_NAMES[chart_code])
        print("#" * 72)

        for year in COLLECTION_YEARS:
            collection = None
            if year in FIXED_YEARS:
                collection = load_fixed_year(year, chart_code)

            if collection is None:
                if opener is None:
                    opener = create_http_opener()
                collection = collect_year(
                    year,
                    opener,
                    chart_code,
                )
            chart_collections.append(collection)

        collections_by_chart[chart_code] = chart_collections

    all_collections = [
        collection
        for chart_collections in collections_by_chart.values()
        for collection in chart_collections
    ]
    save_collection_report(all_collections)

    for collection in all_collections:
        save_year_entries(collection)
        validate_collection(collection)

    analysis_collections_by_chart = {
        chart_code: [
            collection
            for collection in chart_collections
            if collection["year"] in ANALYSIS_YEARS
        ]
        for chart_code, chart_collections in collections_by_chart.items()
    }

    alias_lookup = build_alias_lookup()
    matched_by_chart = {}
    counts_by_chart = {}
    alias_counts_by_chart = {}

    for chart_code, chart_collections in analysis_collections_by_chart.items():
        counts_by_year = {}
        alias_counts_by_year = {}
        chart_matches = []

        for collection in chart_collections:
            counts, alias_counts, matched_entries = count_target_artists(
                collection,
                alias_lookup,
            )
            year = collection["year"]
            counts_by_year[year] = counts
            alias_counts_by_year[year] = alias_counts
            chart_matches.extend(matched_entries)

        counts_by_chart[chart_code] = counts_by_year
        alias_counts_by_chart[chart_code] = alias_counts_by_year
        matched_by_chart[chart_code] = chart_matches

    results = build_results(counts_by_chart[CHART_CODE])
    save_comparison_csv(
        results,
        analysis_collections_by_chart[CHART_CODE],
        alias_counts_by_chart[CHART_CODE],
    )
    save_match_details(matched_by_chart[CHART_CODE])
    save_site(matched_by_chart, analysis_collections_by_chart)
    print_results(
        results
    )

    print()
    print("=" * 76)
    print("すべての処理が完了しました。")
    print("=" * 76)

    print()
    print("収集状況レポート:")
    print(
        COLLECTION_REPORT_FILE.resolve()
    )

    print()
    print("3年間比較CSV:")
    print(
        COMPARISON_FILE.resolve()
    )

    print()
    print("カウント根拠明細:")
    print(
        MATCH_DETAILS_FILE.resolve()
    )

    print()
    print("勢力図サイト:")
    print(
        SITE_FILE.resolve()
    )


if __name__ == "__main__":
    main()

