import streamlit as st
import requests
import pandas as pd

from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo


# -------------------------------------------------
# 기본 설정
# -------------------------------------------------
st.set_page_config(
    page_title="YouTube 경쟁사 모니터링",
    page_icon="📺",
    layout="wide"
)

KST = ZoneInfo("Asia/Seoul")
UTC = ZoneInfo("UTC")


# -------------------------------------------------
# YouTube API 함수
# -------------------------------------------------
def to_youtube_time(dt_kst):
    """한국시간 datetime을 YouTube API용 UTC ISO 형식으로 변환"""
    return dt_kst.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def search_youtube(api_key, query, start_dt, end_dt, max_results=50):
    """
    검색어 + 기간 기준으로 YouTube 영상을 검색하고
    영상 ID 목록을 반환
    """
    search_url = "https://www.googleapis.com/youtube/v3/search"

    video_ids = []
    next_page_token = None

    while len(video_ids) < max_results:
        batch_size = min(50, max_results - len(video_ids))

        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "date",
            "maxResults": batch_size,
            "publishedAfter": to_youtube_time(start_dt),
            "publishedBefore": to_youtube_time(end_dt),
            "key": api_key,
        }

        if next_page_token:
            params["pageToken"] = next_page_token

        response = requests.get(search_url, params=params, timeout=30)

        if response.status_code != 200:
            raise Exception(
                f"YouTube 검색 API 오류 ({response.status_code})\n\n"
                f"{response.text}"
            )

        data = response.json()

        for item in data.get("items", []):
            video_id = item.get("id", {}).get("videoId")

            if video_id:
                video_ids.append(video_id)

        next_page_token = data.get("nextPageToken")

        if not next_page_token:
            break

    return video_ids[:max_results]


def get_video_details(api_key, video_ids, search_query):
    """
    영상 ID를 기준으로 상세 정보 및 통계 수집
    """
    if not video_ids:
        return []

    videos_url = "https://www.googleapis.com/youtube/v3/videos"

    results = []

    # videos.list는 최대 50개씩 조회
    for i in range(0, len(video_ids), 50):
        ids = video_ids[i:i + 50]

        params = {
            "part": "snippet,statistics",
            "id": ",".join(ids),
            "key": api_key,
        }

        response = requests.get(videos_url, params=params, timeout=30)

        if response.status_code != 200:
            raise Exception(
                f"YouTube 영상 정보 API 오류 ({response.status_code})\n\n"
                f"{response.text}"
            )

        data = response.json()

        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            statistics = item.get("statistics", {})

            published_at = snippet.get("publishedAt")

            if published_at:
                published_dt = datetime.fromisoformat(
                    published_at.replace("Z", "+00:00")
                ).astimezone(KST)

                published_text = published_dt.strftime("%Y-%m-%d %H:%M")
            else:
                published_text = ""

            video_id = item.get("id")

            results.append({
                "검색어": search_query,
                "게시일": published_text,
                "제목": snippet.get("title", ""),
                "채널명": snippet.get("channelTitle", ""),
                "조회수": int(statistics.get("viewCount", 0)),
                "좋아요": int(statistics.get("likeCount", 0)),
                "댓글수": int(statistics.get("commentCount", 0)),
                "URL": f"https://www.youtube.com/watch?v={video_id}",
            })

    return results


# -------------------------------------------------
# 화면
# -------------------------------------------------
st.title("📺 YouTube 경쟁사 모니터링")

st.caption(
    "YouTube 전체에서 특정 브랜드·키워드가 언급된 영상을 기간별로 수집합니다."
)

st.divider()


# -------------------------------------------------
# API Key
# -------------------------------------------------
try:
    API_KEY = st.secrets["YOUTUBE_API_KEY"]
except Exception:
    API_KEY = None


if not API_KEY:
    st.warning(
        "YouTube API Key가 아직 등록되지 않았습니다. "
        "Streamlit Secrets에 `YOUTUBE_API_KEY`를 등록해야 수집할 수 있습니다."
    )


# -------------------------------------------------
# 검색 조건
# -------------------------------------------------
col1, col2 = st.columns([2, 1])

with col1:
    query = st.text_input(
        "🔎 검색어",
        value="하나투어",
        placeholder="예: 하나투어"
    )

with col2:
    max_results = st.selectbox(
        "📦 최대 수집량",
        [20, 50, 100],
        index=1
    )


period = st.radio(
    "📅 조회 기간",
    ["오늘", "최근 7일", "최근 30일", "직접 설정"],
    index=1,
    horizontal=True
)


now_kst = datetime.now(KST)

if period == "오늘":

    start_dt = datetime.combine(
        now_kst.date(),
        time.min,
        tzinfo=KST
    )

    end_dt = now_kst

elif period == "최근 7일":

    start_dt = datetime.combine(
        now_kst.date() - timedelta(days=6),
        time.min,
        tzinfo=KST
    )

    end_dt = now_kst

elif period == "최근 30일":

    start_dt = datetime.combine(
        now_kst.date() - timedelta(days=29),
        time.min,
        tzinfo=KST
    )

    end_dt = now_kst

else:

    date_col1, date_col2 = st.columns(2)

    with date_col1:
        start_date = st.date_input(
            "시작일",
            value=now_kst.date() - timedelta(days=6)
        )

    with date_col2:
        end_date = st.date_input(
            "종료일",
            value=now_kst.date()
        )

    start_dt = datetime.combine(
        start_date,
        time.min,
        tzinfo=KST
    )

    # 종료일 전체를 포함
    if end_date == now_kst.date():
        end_dt = now_kst
    else:
        end_dt = datetime.combine(
            end_date + timedelta(days=1),
            time.min,
            tzinfo=KST
        )


st.caption(
    f"수집 범위: "
    f"{start_dt.strftime('%Y-%m-%d %H:%M')} "
    f"~ {end_dt.strftime('%Y-%m-%d %H:%M')} (한국시간)"
)


# -------------------------------------------------
# 수집 실행
# -------------------------------------------------
if st.button(
    "📊 YouTube 수집 시작",
    type="primary",
    use_container_width=True
):

    if not API_KEY:
        st.error("먼저 Streamlit Secrets에 YouTube API Key를 등록해 주세요.")

    elif not query.strip():
        st.error("검색어를 입력해 주세요.")

    elif start_dt >= end_dt:
        st.error("종료일은 시작일보다 뒤여야 합니다.")

    else:

        try:

            with st.spinner("YouTube 데이터를 수집하고 있습니다..."):

                video_ids = search_youtube(
                    api_key=API_KEY,
                    query=query.strip(),
                    start_dt=start_dt,
                    end_dt=end_dt,
                    max_results=max_results
                )

                rows = get_video_details(
                    api_key=API_KEY,
                    video_ids=video_ids,
                    search_query=query.strip()
                )

            if not rows:

                st.info(
                    "선택한 기간에 해당 검색어로 검색된 영상이 없습니다."
                )

            else:

                df = pd.DataFrame(rows)

                df = df.sort_values(
                    "게시일",
                    ascending=False
                ).reset_index(drop=True)

                # ------------------------------
                # 요약 지표
                # ------------------------------
                st.success(
                    f"총 {len(df):,}개의 영상을 수집했습니다."
                )

                m1, m2, m3, m4 = st.columns(4)

                with m1:
                    st.metric(
                        "수집 영상",
                        f"{len(df):,}개"
                    )

                with m2:
                    st.metric(
                        "총 조회수",
                        f"{df['조회수'].sum():,}"
                    )

                with m3:
                    st.metric(
                        "총 좋아요",
                        f"{df['좋아요'].sum():,}"
                    )

                with m4:
                    st.metric(
                        "총 댓글",
                        f"{df['댓글수'].sum():,}"
                    )

                st.divider()

                # ------------------------------
                # 결과표
                # ------------------------------
                st.subheader("📋 수집 결과")

                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "URL": st.column_config.LinkColumn(
                            "영상 링크",
                            display_text="YouTube 열기"
                        ),
                        "조회수": st.column_config.NumberColumn(
                            "조회수",
                            format="%d"
                        ),
                        "좋아요": st.column_config.NumberColumn(
                            "좋아요",
                            format="%d"
                        ),
                        "댓글수": st.column_config.NumberColumn(
                            "댓글수",
                            format="%d"
                        ),
                    }
                )

                # ------------------------------
                # CSV 다운로드
                # ------------------------------
                csv = df.to_csv(
                    index=False
                ).encode("utf-8-sig")

                st.download_button(
                    "📥 CSV 다운로드",
                    csv,
                    file_name=f"youtube_{query}_{now_kst.strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv"
                )

        except Exception as e:

            st.error("데이터 수집 중 오류가 발생했습니다.")

            st.code(str(e))
