# 기술 선정표

확인일: 2026-10-12. 공식 GitHub 원문과 설치된 패키지 메타데이터를 확인했다. 공식 문서 웹사이트 일부는 클라우드 네트워크의 403 응답으로 접근 불가였다. 아래 공식 저장소 문서를 대체 근거로 사용했다. 카카오 REST 문서 웹사이트 직접 열람은 미완료다.

| 영역 | 선택·지원·이유 | 운영 방법·제약 |
|---|---|---|
| 웹·실행 | Django 5.2.18 LTS, Python 3.12.14. 5.2 공식 문서는 3년 이상 보안 지원과 Python 3.12 지원을 명시. 5.2.18은 2026-10-06 보안 수정 릴리스. | 서버 렌더링, 공식 Django ORM·세션·CSRF·비밀번호 해시·검증 사용. |
| DB·접근 | Python 내장 SQLite, 실제 파일 DB. Django의 공식 IMMEDIATE 설정. | 모든 업무 쓰기를 원자적 트랜잭션으로 직렬화. 서버 역할·소유자 필터. DB는 브라우저에 직접 노출하지 않으며 서비스 OS 계정만 파일 접근. 마이그레이션·온라인 backup API·복원 점검. 단일 호스트와 로컬 영속 디스크 필수. |
| 인증 | django-allauth 65.19.7 Kakao provider, Django auth. PyPI 배포·공식 저장소 현재 릴리스 확인. 별도 장기지원 보장 미확인. | 총무 카카오 OAuth, 판매자·운영자 발급 계정. 최초 운영자는 터미널 일회성 생성. 일상 운영은 화면에서 처리. POST 로그아웃, 비활성 사용자·프로필을 요청마다 검사. 판매자 삭제 시 기존 세션 API 차단. |
| 자동 갱신 | fetch 기반 3초 조회, 페이지당 20건 | 탭당 기본 20회/분. 판매자는 필터와 별개 대기 조회를 추가하여 보통 40회/분, 상세 페이지는 최대 60회/분. 지연은 정상 네트워크에서 3초+요청시간. 재연결 시 전체 현재 상태 조회. 알림은 이벤트 스트림에 의존하지 않음. |
| 자동 취소 | Django expire_orders 별도 장기 실행 작업, 1초 검사 | 매회 최대 100건, 브라우저 독립. 원본 deadline과 recorded_at 분리. 작업이 늦어도 수락 API가 DB 시각을 검사. 프로세스 관리자 재시작 필요. |
| 배포 | Linux + Gunicorn 26.2.0의 안정 WSGI sync worker + HTTPS 프록시, 단일 호스트 | 예시 2 workers. HTTP/2 beta·dirty arbiter 사용 안 함. 호스팅 미정, 비용 미확정, 유료 계약 안 함. 단일 인스턴스 장애 동안 업무 중단. 파일 DB 보존·오프호스트 백업·복구 검증 필요. |
| UI | 자체 한국어 HTML/CSS/JS, 별도 런타임 UI 의존성 없음 | 모바일 중심. 가칭 브랜드와 예시 카페 구분. |
| 시험 | Django unittest, Playwright 1.62.1 dev dependency + Chromium | 자동 동시성·권한·브라우저 흐름. 실제 휴대폰·카카오 OAuth 시험은 별도 필요. |

## 공식 근거

- https://github.com/django/django
- https://github.com/django/django/blob/stable/5.2.x/docs/releases/5.2.txt
- https://github.com/django/django/blob/stable/5.2.x/docs/releases/5.2.18.txt — 보안·데이터 손실 수정 공지 확인.
- https://github.com/django/django/blob/stable/5.2.x/docs/ref/databases.txt — IMMEDIATE, 잠금 한계. 대규모 동시 쓰기를 SQLite가 해결한다고 주장하지 않는다.
- https://github.com/pennersr/django-allauth
- https://github.com/pennersr/django-allauth/blob/main/docs/socialaccount/providers/kakao.rst — 공식 제공자와 callback 주소 확인.
- https://developers.kakao.com/docs/ko/kakaologin/rest-api — 현재 환경 직접 접속 403, 실제 앱 생성 후 공식 절차 재확인 필요.
- https://github.com/benoitc/gunicorn/blob/master/SECURITY.md — 지원 26·25, 23 지원 종료 확인.
- https://github.com/benoitc/gunicorn — WSGI 사용, Unix·Python 3.10+ 확인.
- https://www.sqlite.org/backup.html — Python sqlite3.Connection.backup 활용, 공식 웹사이트 현재 직접 접근 미완료.
- https://docs.python.org/3/library/sqlite3.html — 표준 라이브러리 API. 웹 직접 접근 미완료.
- https://github.com/microsoft/playwright
- https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Autoplay — 실기기 확인 필요.

의존성 잠금 파일을 대상으로 pip-audit(Python 공식 생태계 도구)를 2026-10-12 실행: 알려진 취약점 발견 없음. 이는 모든 버그·취약점 부재를 보장하지 않는다. Dependabot 구성 추가, 공개 GitHub PR/푸시·유료 서비스 활성화는 수행하지 않았다.

## 라이선스·외부 코드

외부 예제를 복사하거나 벤더링하지 않았다. Django BSD-3-Clause, django-allauth MIT, Gunicorn MIT, Playwright Apache-2.0. SDK·라이브러리는 패키지로 사용하며 원본 라이선스는 설치 배포물에 포함된다. 패키지 배포 시 라이선스 파일을 유지해야 한다. SQLite는 public domain. 전체 전이 의존성은 requirements.txt·package-lock.json 기준으로 배포물의 라이선스·고지를 유지한다.

추가 확인: 실제 SQLite 엔진 3.53.1이며 공식 `sqlite/sqlite`의 `version-3.53.1/VERSION`과 일치했다. Playwright 공식 `v1.62.1` tag의 Node >=20·Apache-2.0을 확인했다. django-allauth 공식 `65.19.7/pyproject.toml`은 Production/Stable로 분류한다. Python 공식 devguide의 지원 버전 자료도 확인했다.
- https://github.com/sqlite/sqlite/tree/version-3.53.1
- https://github.com/microsoft/playwright/blob/v1.62.1/package.json
- https://github.com/pennersr/django-allauth/blob/65.19.7/pyproject.toml
- https://github.com/python/devguide/blob/main/versions.rst
