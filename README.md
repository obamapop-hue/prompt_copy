# 영차 — 단체 커피 주문 사이트

카톡방에서 링크로 음료를 모으고 총무가 매장에 한 번에 전송하는 웹 앱. **현재 로컬 시연·개발 구현이며 공개 서비스가 아니다.** 서비스명은 영차다. 카카오 앱·호스팅·도메인은 아직 없다. 실제 카카오 로그인·실제 휴대폰 시험·배포는 미완료다.

쉬운 사용법은 [영차 사용법](docs/QUICK_GUIDE.md)을 확인하세요. 화면·권한·주문·알림이 어떻게 이어지는지는 [영차 구조와 작동 방식](docs/HOW_IT_WORKS.md)에 정리했습니다.

## 실행

공개용 파일과 남은 절차는 [공개 준비](docs/DEPLOYMENT.md)에 있습니다. 아직 실제 호스팅에 배포되지 않았습니다.

Python 3.12와 bash 필요. 기존 `/workspace/prompt_copy` 체크아웃 사용. 작업마다 환경은 격리되어 있으므로 요청 없이 Git worktree를 만들지 않는다.

```sh
cd /workspace/prompt_copy
./scripts/install.sh
./scripts/dev.sh
```

별도 터미널에서 자동 취소 작업 실행:

```sh
cd /workspace/prompt_copy
./scripts/worker.sh
```

개발 서버 포트는 8001. HTTP 요청은 내부 검증용이며 클라우드 온보딩 UI의 localhost 공개 미리보기를 제공하지 않는다. 현재 환경에서 Python 서버와 실제 SQLite 파일 DB가 작동한다. 새 작업에서는 서버와 worker를 다시 시작한다.

설치는 잠긴 requirements.txt를 사용하며 `.local/runtime.env`의 개발용 키를 처음 한 번 생성한다. 기존 키·DB·시연 계정은 덮어쓰지 않는다. `.local` 전체는 비공개·Git 제외 대상이다. 개발 DB와 실제 운영 DB는 반드시 분리한다. 시연 계정은 `.local/demo-accounts.json`에 owner-only 권한으로 저장되며 채팅·로그·커밋에 올리지 않는다. 총무 시험용 세션은 Kakao 시험의 대체가 아니다. 공개 화면에 가짜 총무 로그인 버튼을 추가하지 않았다.

루트 `index.html`은 카카오·서버 설정 없이 열 수 있는 영차 홈페이지 미리보기다. 로그인 팝업과 시연용 메뉴 확인만 제공하며 실제 로그인·주문 저장은 하지 않는다. 실제 주문 앱은 Django에서 실행한다.

## 기능

- 총무: 카카오 제공자 연결 코드, 최초 고유 닉네임, 주문방 생성, 링크 공유, 참여 취합, 전송 전 삭제·수량 조절, 마감·전송, 접수 전 전체 취소, 자동 상태 갱신·이력.
- 참여자: 인증 없는 링크, 메뉴·필수 옵션 그룹·추가 옵션·수량 선택, 장바구니, 이름·다중 항목 제출, 본인 원본 제출 결과. 다른 참여자 자료 조회 API 없음.
- 판매자: 발급 계정 로그인, 매장별 주문만 조회, 준비 시간 수락·10~50자 사유 거절·완료, 반복 팝업/음성 알림 활성화, 기간·상태·주문번호·페이지 조회.
- 운영자: 계정 로그인, 매장·메뉴·옵션 관리, 판매자 발급·삭제, 전체 주문 필터·조회. 주문 강제 수정 기능 없음. 승인한 판매자 삭제에 따른 진행 주문 취소만 허용.
- DB 원본·수량 변경·처리 이력·가격 스냅샷·서버 금액 계산·요청 재시도·동시성 통제·DB 시각 5분 기한.

## 시험

```sh
source .local/runtime.env
.venv/bin/python manage.py test orders --noinput -v 2
.venv/bin/python manage.py check
.venv/bin/python -m pip check
```

브라우저 시험은 실제 서버·worker·시연 데이터가 필요하다. 새 시연 주문을 만든다. 먼저 로컬 시험용 총무 세션을 생성한다. 인증은 시험용이며 실제 Kakao OAuth를 검증하지 않는다.

```sh
source .local/runtime.env
.venv/bin/python manage.py prepare_browser_test
npm ci --ignore-scripts --cache /tmp/moa-npm-cache
# Chromium이 /usr/bin/chromium에 있어야 한다. 다른 경로는 CHROMIUM_PATH 지정.
npm run test:browser
```

결과: [인수 시험 기록](docs/ACCEPTANCE.md). [정책 승인 기록](docs/DECISIONS.md), [기술 선정 근거](docs/TECHNOLOGY.md), [DB 관계](docs/DATABASE.md), [운영·배포·복구](docs/OPERATIONS.md).

## 카카오와 운영 준비

[운영 안내](docs/OPERATIONS.md)에 Kakao 앱 생성·callback·키 설정·최초 운영자 생성·백업·복구 절차가 있다. 실제 비밀값은 `.env.example`에 기입하거나 커밋하지 말고 배포 환경의 보안 설정에 넣는다. 호스팅·도메인·유료 계약은 승인 후 진행한다.

공개 전 필수: Kakao 실제 로그인·로그아웃·원래 화면 복귀, 카카오톡 내부 브라우저, 두 실제 기기 연동, 실제 매장 알림음, HTTPS 배포·영속 디스크·worker 감독·오프호스트 백업/복구, 개인정보 보관·삭제와 영업 정책 결정.
