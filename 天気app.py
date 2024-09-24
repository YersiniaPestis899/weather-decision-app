import streamlit as st
import requests
import json
from datetime import datetime
import boto3
import googlemaps
import pandas as pd
import folium
from streamlit_folium import folium_static
import os
from dotenv import load_dotenv
import logging

# ロギングの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# API keys and endpoints
OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
AWS_REGION = "ap-northeast-1"

# Initialize Google Maps client
gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

def authenticate_aws(aws_access_key_id, aws_secret_access_key):
    try:
        # STSクライアントを使用して認証をテスト
        sts_client = boto3.client('sts',
                                  aws_access_key_id=aws_access_key_id,
                                  aws_secret_access_key=aws_secret_access_key,
                                  region_name=AWS_REGION)
        
        # GetCallerIdentityを呼び出してクレデンシャルをテスト
        caller_identity = sts_client.get_caller_identity()
        account_id = caller_identity['Account']
        user_id = caller_identity['UserId']
        arn = caller_identity['Arn']

        logger.info(f"認証成功: アカウントID: {account_id}, ユーザーID: {user_id}, ARN: {arn}")

        st.success("AWS認証成功:")
        st.write(f"アカウントID: {account_id}")
        st.write(f"ユーザーID: {user_id}")
        st.write(f"ARN: {arn}")

        # Bedrockクライアントの初期化
        bedrock_client = boto3.client('bedrock-runtime',
                                      aws_access_key_id=aws_access_key_id,
                                      aws_secret_access_key=aws_secret_access_key,
                                      region_name=AWS_REGION)
        
        # Bedrockの操作をテスト
        models = bedrock_client.list_foundation_models()
        st.success(f"Bedrock認証成功: {len(models['modelSummaries'])}個のモデルが利用可能")

        return bedrock_client
    except Exception as e:
        logger.error(f"AWS認証エラー: {str(e)}")
        st.error(f"AWS認証エラー: {str(e)}")
    
    return None

def get_weather(latitude, longitude):
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={latitude}&lon={longitude}&appid={OPENWEATHERMAP_API_KEY}&units=metric&lang=ja"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"天気情報の取得に失敗: {str(e)}")
        st.error(f"天気情報の取得に失敗しました: {str(e)}")
        return None

def get_weather_forecast(latitude, longitude):
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={latitude}&lon={longitude}&appid={OPENWEATHERMAP_API_KEY}&units=metric&lang=ja"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"天気予報の取得に失敗: {str(e)}")
        st.error(f"天気予報の取得に失敗しました: {str(e)}")
        return None

def get_coordinates(address):
    try:
        result = gmaps.geocode(address)
        if result:
            location = result[0]['geometry']['location']
            return (location['lat'], location['lng'])
        else:
            raise ValueError(f"住所が見つかりませんでした: {address}")
    except Exception as e:
        logger.error(f"座標の取得に失敗: {str(e)}")
        st.error(f"座標の取得に失敗しました: {str(e)}")
        return None

def get_travel_info(origin, destination):
    try:
        now = datetime.now()
        directions_result = gmaps.directions(origin, destination, mode="driving", departure_time=now)
        if directions_result:
            leg = directions_result[0]['legs'][0]
            return {
                'distance': leg['distance']['text'],
                'duration': leg['duration']['text'],
                'duration_in_traffic': leg['duration_in_traffic']['text']
            }
        else:
            raise ValueError(f"経路が見つかりませんでした: {origin} から {destination}")
    except Exception as e:
        logger.error(f"移動情報の取得に失敗: {str(e)}")
        st.error(f"移動情報の取得に失敗しました: {str(e)}")
        return None
def process_forecast_data(forecast_data):
    processed_data = []
    for item in forecast_data['list']:
        date = datetime.fromtimestamp(item['dt'])
        if date.hour == 12:  # 正午のデータのみを使用
            processed_data.append({
                '日付': date.strftime('%Y-%m-%d'),
                '天気': item['weather'][0]['description'],
                '気温': f"{item['main']['temp']:.1f}°C",
                '湿度': f"{item['main']['humidity']}%",
                '風速': f"{item['wind']['speed']} m/s"
            })
    return pd.DataFrame(processed_data)

def create_map(start_coords, end_coords):
    center_lat = (start_coords[0] + end_coords[0]) / 2
    center_lng = (start_coords[1] + end_coords[1]) / 2
    
    m = folium.Map(location=[center_lat, center_lng], zoom_start=6)
    
    folium.Marker(
        start_coords,
        popup="出発地",
        icon=folium.Icon(color="red", icon="info-sign"),
    ).add_to(m)
    
    folium.Marker(
        end_coords,
        popup="目的地",
        icon=folium.Icon(color="green", icon="info-sign"),
    ).add_to(m)
    
    folium.PolyLine(
        locations=[start_coords, end_coords],
        color="blue",
        weight=2,
        opacity=0.8
    ).add_to(m)
    
    return m

def analyze_outing(weather_data, forecast_data, travel_info, purpose, additional_question, aws_client):
    forecast_summary = process_forecast_data(forecast_data)
    forecast_text = forecast_summary.to_string(index=False)

    user_message = f"""
    あなたは外出判断のアシスタントです。以下の情報に基づいて、目的地に行くべきか、行かないべきかを判断し、理由とともに回答してください。

    外出目的: {purpose}

    現在の天気情報:
    - 天気: {weather_data['weather'][0]['description']}
    - 気温: {weather_data['main']['temp']}°C
    - 湿度: {weather_data['main']['humidity']}%
    - 風速: {weather_data['wind']['speed']} m/s

    5日間の天気予報:
    {forecast_text}

    移動情報:
    - 移動距離: {travel_info['distance']}
    - 通常の所要時間: {travel_info['duration']}
    - 交通状況を考慮した所要時間: {travel_info['duration_in_traffic']}

    これらの情報を考慮して、以下の質問に答えてください：
    1. 目的地に今日行くべきでしょうか？それとも別の日に行くべきでしょうか？
    2. もし別の日に行くべきだと判断した場合、5日間の予報の中でどの日が最適だと思われますか？
    3. 外出目的を達成するのに、現在および今後の天候はどのような影響を与えると予想されますか？
    4. 移動時間や交通状況を考慮すると、外出のタイミングについて何か助言はありますか？

    追加の質問: {additional_question}

    回答は簡潔にまとめ、理由も添えて説明してください。また、追加の質問にも必ず答えてください。
    """

    messages = [
        {
            "role": "user",
            "content": user_message
        }
    ]

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 200000,
        "messages": messages,
        "temperature": 0.5,
        "top_p": 0.9,
    })

    try:
        response = aws_client.invoke_model(
            modelId="anthropic.claude-3-5-sonnet-20240620-v1:0",
            contentType="application/json",
            accept="application/json",
            body=body
        )
        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']
    except Exception as e:
        logger.error(f"AI分析中にエラーが発生しました: {str(e)}")
        st.error(f"AI分析中にエラーが発生しました: {str(e)}")
        return "AI分析に失敗しました。基本的な情報のみ表示します。"

def main():
    st.set_page_config(page_title="外出判断アプリ", page_icon="🏙️", layout="wide")

    st.title("🏠🚗 外出判断アプリ")
    st.write("天気と交通情報に基づいて、目的地に行くべきかどうかを判断します。")

    # IAMユーザーログイン
    aws_access_key_id = st.text_input("AWS Access Key ID", type="password")
    aws_secret_access_key = st.text_input("AWS Secret Access Key", type="password")

    if aws_access_key_id and aws_secret_access_key:
        aws_client = authenticate_aws(aws_access_key_id, aws_secret_access_key)
        if aws_client:
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("📍 場所情報")
                start_location = st.text_input("出発地", "")
                end_location = st.text_input("目的地", "")
                purpose = st.text_input("外出の目的（例：買い物、観光、ビジネス）", "")
                additional_question = st.text_input("追加の質問（オプション）", "")

            if st.button("外出判断を実行", key="run_analysis"):
                with st.spinner("分析中..."):
                    try:
                        start_coords = get_coordinates(start_location)
                        end_coords = get_coordinates(end_location)
                        if start_coords and end_coords:
                            weather_data = get_weather(start_coords[0], start_coords[1])
                            forecast_data = get_weather_forecast(start_coords[0], start_coords[1])
                            travel_info = get_travel_info(start_location, end_location)

                            if weather_data and forecast_data and travel_info:
                                with col2:
                                    st.subheader("🗺️ 位置情報")
                                    map = create_map(start_coords, end_coords)
                                    folium_static(map)

                                st.subheader("🌤️ 現在の天気情報")
                                weather_col1, weather_col2 = st.columns(2)
                                with weather_col1:
                                    st.metric("天気", weather_data['weather'][0]['description'])
                                    st.metric("気温", f"{weather_data['main']['temp']}°C")
                                with weather_col2:
                                    st.metric("湿度", f"{weather_data['main']['humidity']}%")
                                    st.metric("風速", f"{weather_data['wind']['speed']} m/s")

                                st.subheader("📅 5日間の天気予報")
                                forecast_df = process_forecast_data(forecast_data)
                                st.dataframe(forecast_df, hide_index=True)

                                st.subheader("🚗 移動情報")
                                travel_col1, travel_col2, travel_col3 = st.columns(3)
                                with travel_col1:
                                    st.metric("距離", travel_info['distance'])
                                with travel_col2:
                                    st.metric("通常の所要時間", travel_info['duration'])
                                with travel_col3:
                                    st.metric("交通状況考慮時間", travel_info['duration_in_traffic'])

                                recommendation = analyze_outing(weather_data, forecast_data, travel_info, purpose, additional_question, aws_client)

                                st.subheader("🤖 AIによる外出判断")
                                st.info(recommendation)
                            else:
                                st.error("天気情報または移動情報の取得に失敗しました。")
                        else:
                            st.error("座標の取得に失敗しました。正しい住所を入力してください。")
                    except Exception as e:
                        st.error(f"エラーが発生しました: {str(e)}")
        else:
            st.error("AWS認証に失敗しました。認証情報を確認してください。")
    else:
        st.warning("AWS認証情報を入力してください。")

if __name__ == "__main__":
    main()