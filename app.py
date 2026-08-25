import streamlit as st
import requests
import pandas as pd

from datetime import datetime, time, timedelta
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
# 공통 함수
# -------------------------------------------------
def to_youtube_time(dt_kst):
    """한국시간 → YouTube API용 UTC ISO 형식"""
    return dt_kst.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_text(text):
    if not text:
        return ""

    return (
        text.lower()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
    )


def is_relevant_video(query, title, description, channel):
    """
    YouTube 검색 결과 중 검색어가 실제 콘텐츠에 포함된 영상만 유지.
    제목 + 설명 + 채널명을 기준으로 검사.
    """
    query_norm = normalize_text(query)

    combined = normalize_text(
        f"{title} {description} {channel}"
    )

    return query_norm in combined


# -------------------------------------------------
# YouTube 검색
# -------------------------------------------------
def search_youtube(api_key, query, start_dt, end_dt, max_results=50):

    search_url = "https://www.googleapis.com/youtube/v3/search"

    video_ids = []
    next_page_token = None

    # 노이즈 제거 후에도 충분한 결과를 확보하기 위해
    # 요청 수를 조금 넉넉하게 가져옴
    target_fetch = min(max_results * 2, 200)

    while len(video_ids) < target_fetch:

        batch_size = min(50, target_fetch - len(video_ids))

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

        response = requests.get(
            search_url,
            params=params,
            timeout=30
        )

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

    return video_ids


# -------------------------------------------------
# 영상 상세정보
# -------------------------------------------------
def get_video_details(api_key, video_ids, search_query, max_results):

    if not video_ids:
        return []

    videos_url = "https://www.googleapis.com/youtube/v3/videos"

    results = []

    for i in range(0, len(video_ids), 50):

        ids = video_ids[i:i + 50]

        params = {
            "part": "snippet,statistics",
            "id": ",".join(ids),
            "key": api_key,
        }

        response = requests.get(
            videos_url,
            params=params,
            timeout=30
        )

        if response.status_code != 200:
            raise Exception(
                f"YouTube 영상 정보 API 오류 ({response.status_code})\n\n"
                f"{response.text}"
            )

        data = response.json()

        for item in data.get("items", []):

            snippet = item.get("snippet", {})
            statistics = item.get("statistics", {})

            title = snippet.get("title", "")
            description = snippet.get("description", "")
            channel = snippet.get("channelTitle", "")

            # -------------------------------------
            # 관련성 필터
            # -------------------------------------
            if not is_relevant_video(
                search_query,
                title,
                description,
                channel
            ):
                continue

            published_at = snippet.get("publishedAt")

            if published_at:

                published_dt = datetime.fromisoformat(
                    published_at.replace("Z", "+00:00")
                ).astimezone(KST)

                published_text = published_dt.strftime(
                    "%Y-%m-%d %H:%M"
                )

                published_date = published_dt.date()

            else:

                published_text = ""
                published_date = None

            video_id = item.get("id")

            views = int(statistics.get("viewCount", 0))
            likes = int(statistics.get("likeCount", 0))
            comments = int(statistics.get("commentCount", 0))

            results.append({
                "검색어": search_query,
                "게시일": published_text,
                "게시날짜": published_date,
                "제목": title,
                "채널명": channel,
                "조회수": views,
                "좋아요": likes,
                "댓글수": comments,
                "총반응": likes + comments,
                "URL": f"https://www.youtube.com/watch?v={video_id}",
            })

            if len(results) >= max_results:
                return results

    return results


# -------------------------------------------------
# 제목
# -------------------------------------------------
st.title("📺 YouTube 경쟁사 모니터링")

st.caption(
    "YouTube 전체에서 특정 브랜드·키워드가 언급된 영상을 "
    "기간별로 수집하고 주요 반응을 확인합니다."
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
        "Streamlit Secrets에 `YOUTUBE_API_KEY`를 등록해야 합니다."
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
    f"~ {end_dt.strftime('%Y-%m-%d %H:%M')} "
    f"(한국시간)"
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

        st.error(
            "먼저 Streamlit Secrets에 "
            "YouTube API Key를 등록해 주세요."
        )

    elif not query.strip():

        st.error("검색어를 입력해 주세요.")

    elif start_dt >= end_dt:

        st.error(
            "종료일은 시작일보다 뒤여야 합니다."
        )

    else:

        try:

            with st.spinner(
                "YouTube 데이터를 수집하고 있습니다..."
            ):

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
                    search_query=query.strip(),
                    max_results=max_results
                )


            if not rows:

                st.info(
                    "선택한 기간에 검색어와 직접 관련된 "
                    "영상을 찾지 못했습니다."
                )

            else:

                df = pd.DataFrame(rows)

                df = df.sort_values(
                    "게시일",
                    ascending=False
                ).reset_index(drop=True)


                # ---------------------------------
                # 오늘 신규
                # ---------------------------------
                today = now_kst.date()

                today_df = df[
                    df["게시날짜"] == today
                ]

                today_count = len(today_df)


                # ---------------------------------
                # 요약
                # ---------------------------------
                st.success(
                    f"관련 영상 총 {len(df):,}개를 수집했습니다."
                )

                st.subheader("📌 핵심 현황")

                m1, m2, m3, m4, m5 = st.columns(5)

                m1.metric(
                    "오늘 신규",
                    f"{today_count:,}개"
                )

                m2.metric(
                    "기간 내 영상",
                    f"{len(df):,}개"
                )

                m3.metric(
                    "총 조회수",
                    f"{df['조회수'].sum():,}"
                )

                m4.metric(
                    "총 좋아요",
                    f"{df['좋아요'].sum():,}"
                )

                m5.metric(
                    "총 댓글",
                    f"{df['댓글수'].sum():,}"
                )


                st.divider()


                # ---------------------------------
                # 일자별 업로드 현황
                # ---------------------------------
                st.subheader("📈 일자별 신규 영상")

                daily = (
                    df.groupby("게시날짜")
                    .size()
                    .reset_index(name="영상수")
                    .sort_values("게시날짜")
                )

                daily["게시날짜"] = (
                    daily["게시날짜"]
                    .astype(str)
                )

                st.bar_chart(
                    daily,
                    x="게시날짜",
                    y="영상수",
                    use_container_width=True
                )


                st.divider()


                # ---------------------------------
                # TOP 콘텐츠
                # ---------------------------------
                st.subheader("🔥 주요 콘텐츠")

                top_col1, top_col2 = st.columns(2)


                with top_col1:

                    st.markdown("#### 👀 조회수 TOP 5")

                    top_views = (
                        df.sort_values(
                            "조회수",
                            ascending=False
                        )
                        .head(5)
                    )

                    for _, row in top_views.iterrows():

                        st.markdown(
                            f"**[{row['제목']}]({row['URL']})**"
                        )

                        st.caption(
                            f"{row['채널명']} · "
                            f"조회 {row['조회수']:,} · "
                            f"좋아요 {row['좋아요']:,} · "
                            f"댓글 {row['댓글수']:,}"
                        )


                with top_col2:

                    st.markdown("#### 💬 반응 TOP 5")

                    top_reactions = (
                        df.sort_values(
                            "총반응",
                            ascending=False
                        )
                        .head(5)
                    )

                    for _, row in top_reactions.iterrows():

                        st.markdown(
                            f"**[{row['제목']}]({row['URL']})**"
                        )

                        st.caption(
                            f"{row['채널명']} · "
                            f"총 반응 {row['총반응']:,} · "
                            f"좋아요 {row['좋아요']:,} · "
                            f"댓글 {row['댓글수']:,}"
                        )


                st.divider()


                # ---------------------------------
                # 전체 결과
                # ---------------------------------
                st.subheader("📋 전체 수집 결과")

                display_df = df.drop(
                    columns=[
                        "게시날짜",
                        "총반응"
                    ]
                )

                st.dataframe(
                    display_df,
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


                # ---------------------------------
                # CSV
                # ---------------------------------
                csv = (
                    display_df
                    .to_csv(index=False)
                    .encode("utf-8-sig")
                )

                st.download_button(
                    "📥 CSV 다운로드",
                    csv,
                    file_name=(
                        f"youtube_{query}_"
                        f"{now_kst.strftime('%Y%m%d_%H%M')}.csv"
                    ),
                    mime="text/csv"
                )


        except Exception as e:

            st.error(
                "데이터 수집 중 오류가 발생했습니다."
            )

            st.code(str(e))
