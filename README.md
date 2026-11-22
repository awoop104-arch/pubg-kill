[README.md](https://github.com/user-attachments/files/35234670/README.md)
# -# PUBG 킬내기 관리 웹 배포 패키지

솔로 / 듀오 / 스쿼드 모드별 팀 구성, 티어, 감점(`0`, `-1`~`-10`), 킬핸디(`0`~`10`), 팀별 완료 합계 및 초기화를 웹 브라우저에서 함께 사용할 수 있도록 만든 배포용 파일 세트입니다.

## 포함된 파일
- `app.py`: FastAPI 백엔드 + 웹 UI
- `requirements.txt`: 파이썬 패키지 목록
- `render.yaml`: Render 무료 웹 서비스 배포 설정

## 무료 외부 배포 순서 (GitHub + Render)
1. **GitHub에 새 저장소 생성** 후 `app.py`, `requirements.txt`, `render.yaml` 파일을 업로드합니다.
2. **Render**에 가입/로그인한 뒤 **New +** -> **Web Service**를 선택하고 해당 GitHub 저장소를 연결합니다.
3. 설정 확인:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** `Free`
4. 배포가 완료되면 발급되는 `https://...` 주소를 함께 쓸 사람들에게 공유합니다.

## 로컬에서 미리 테스트하기
```bash
pip install -r requirements.txt
python app.py
```
브라우저에서 `http://localhost:8000` 으로 접속해 동작을 확인할 수 있습니다.
