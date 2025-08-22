## ✨ 주요 기능

### 🤖 AI 기반 추천
- OpenAI GPT-4 기반 지능형 강의 추천
- 관심 분야 분석을 통한 맞춤형 커리큘럼 생성
- 졸업 요건을 고려한 자동 학점 계산

### 📚 커리큘럼 관리
- 개인별 커리큘럼 생성 및 저장
- 실시간 커리큘럼 편집 (강의 추가/삭제/이동)
- 선이수 과목 및 필요 지식 자동 체크

### 💬 대화형 인터페이스
- WebSocket 기반 실시간 채팅
- 자연어 처리를 통한 직관적인 상호작용
- 단계별 가이드와 조건 설정

### 🎯 맞춤 조건 지원
- 졸업: 최소 학점으로 졸업 가능한 커리큘럼 설계
- 팀플 제외: 팀 프로젝트 진행 강의 최소화
- 선호 교수: 특정 교수의 강의 우선 배정
- 재수강 포함: 재수강 필요 과목 포함 배정

<br>

## 🛠️ 기술 스택

### Backend
- **FastAPI**: 고성능 비동기 웹 프레임워크
- **SQLAlchemy**: ORM 및 데이터베이스 관리
- **MySQL**: 관계형 데이터베이스
- **WebSocket**: 실시간 양방향 통신

### AI
- **OpenAI GPT-4**: 자연어 처리 및 추천 알고리즘
- **Python asyncio**: 비동기 처리

### Infrastructure
- **Docker**: 컨테이너화
- **Docker Compose**: 멀티 컨테이너 관리

<br>

## 📋 시스템 요구사항

- Python 3.11+
- MySQL 8.0+
- Docker & Docker Compose
- OpenAI API Key

<br>

## 🚀 Docker 실행

### 컨테이너 실행
```bash
# 컨테이너 빌드 및 실행
docker-compose up --build

# 백그라운드 실행
docker-compose up -d
```

<br>

## 🏗️ 프로젝트 구조

```
app/
├── main.py                   # FastAPI 애플리케이션 진입점
├── core/
│   ├── config.py             # 설정 관리
│   └── constants.py          # 상수 정의
├── database/
│   ├── base.py              # SQLAlchemy Base
│   └── connection.py        # DB 연결 관리
├── chat/
│   ├── websocket_handler.py # WebSocket 핸들러
│   ├── chat_models.py       # 채팅 모델
│   └── chat_repository.py   # 채팅 데이터 저장소
├── curriculum/
│   ├── curriculum_models.py     # 커리큘럼 모델
│   ├── curriculum_repository.py # 커리큘럼 데이터 저장소
│   └── service/                 # 커리큘럼 비즈니스 로직
│       ├── curriculum_manager.py
│       ├── curriculum_builder.py
│       ├── curriculum_final_builder.py
│       ├── curriculum_edit_service.py
│       └── curriculum_utils.py
├── lecture/
│   ├── lecture_models.py     # 강의 모델
│   ├── lecture_repository.py # 강의 데이터 저장소
│   └── lecture_service.py    # 강의 서비스
├── recommendation/
│   └── service/
│       ├── gpt_service.py            # GPT API 서비스
│       └── recommendation_service.py # 추천 서비스
├── professor/
│   ├── professor_models.py     # 교수 모델
│   └── professor_repository.py # 교수 데이터 저장소
└── utils/
    ├── completed_data.py      # 이수 완료 데이터
    ├── format_utils.py        # 형식 유틸리티
    └── condition_utils.py     # 조건 처리 유틸리티
```
