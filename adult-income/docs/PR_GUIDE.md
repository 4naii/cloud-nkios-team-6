# 1·6·7단계: PR 머지, 동기화, PR 만들기, 리뷰

용어
- `upstream` = 팀 원본 repo
- `origin` = 내가 fork한 repo

---

## 1단계: 지난 PR 머지 및 각자 repo 동기화

### 1-1. 지난 PR 머지 (팀 repo 관리자가 GitHub에서)

1. 팀 repo → **Pull requests** 탭에서 지난주 PR을 엽니다.
2. 리뷰 승인(Approve)을 받았는지, 충돌(conflict)이 없는지 확인합니다.
3. **Merge pull request** → **Confirm merge**를 누릅니다.

### 1-2. 내 fork를 팀 repo와 동기화 (팀원 각자)

**방법 A: GitHub 웹 (가장 쉬움)**

내 fork 화면에서 **Sync fork** → **Update branch**를 누릅니다.

**방법 B: 터미널**

```bash
git clone https://github.com/<내아이디>/<repo이름>.git   # 처음 한 번만
cd <repo이름>
git remote add upstream https://github.com/<팀아이디>/<repo이름>.git   # 처음 한 번만

git checkout main
git fetch upstream
git merge upstream/main        # 팀 repo 최신 내용을 내 main에 반영
git push origin main           # 내 fork(GitHub)에도 반영
```

`git log --oneline -5`를 실행해서 지난주 PR 커밋이 보이면 동기화가 된 것입니다.

---

## 6단계: PR 만들기

```bash
git checkout main
git pull upstream main                     # 작업 전 다시 최신화
git checkout -b feature/predict-api        # 작업 브랜치

# 이번 작업 파일 복사 후
python -m src.train                        # 모델 생성 확인
python -m scripts.validate                 # 검증 통과 확인
pytest -q                                  # 테스트 통과 확인

git add .
git commit -m "feat: 소득 예측 API와 입력 화면 추가, 임계값 조정으로 >50K 재현율 개선"
git push origin feature/predict-api
```

이후 GitHub에서 PR을 만듭니다.

1. 내 fork 화면에 뜨는 **Compare & pull request**를 누릅니다.
2. 방향이 **base: 팀repo/main ← head: 내fork/feature/predict-api**인지 확인합니다.
3. 제목과 본문은 `docs/PR_DESCRIPTION.md`의 내용을 복사해서 붙여 넣습니다.
4. **Reviewers**에 팀원을 지정하고 **Create pull request**를 누릅니다.

---

## 7단계: 리뷰하기 (팀원 PR을 리뷰할 때)

### 리뷰 방법

1. PR의 **Files changed** 탭에서 코드 줄 옆의 **+**를 눌러 코멘트를 답니다.
2. 직접 실행해 봅니다.
   ```bash
   git fetch upstream pull/<PR번호>/head:review-pr
   git checkout review-pr
   pip install -r requirements.txt
   python -m src.train && python -m scripts.validate && pytest -q
   uvicorn app.main:app --reload     # http://127.0.0.1:8000 에서 화면 확인
   ```
3. **Review changes**에서 다음 중 하나를 고릅니다.
   - Comment: 의견만 남김
   - Approve: 승인
   - Request changes: 수정 요청

### 리뷰 체크리스트

- [ ] README대로 따라 하면 처음부터 실행되는가
- [ ] `scripts.validate` 정확도가 0.85 이상인가
- [ ] test 데이터를 학습이나 튜닝에 쓰지 않았는가 (데이터 누수)
- [ ] 학습과 API에서 같은 전처리 코드를 쓰는가
- [ ] 잘못된 입력(범위 밖 값, 없는 범주, 필수값 누락)을 거부하는가
- [ ] 화면에서 에러가 나면 사용자에게 보여주는가
- [ ] 모델 파일 같은 큰 파일이나 비밀번호가 커밋되지 않았는가

### 리뷰 코멘트 예시

> **[질문]** `choose_threshold`에서 F1 기준으로 임계값을 고른 이유가 있나요? 정확도 기준이면 0.5 근처가 나올 것 같아서요.

> **[제안]** `metrics.json`에 학습 날짜와 sklearn 버전도 기록하면, 나중에 모델을 비교할 때 편할 것 같습니다.

> **[확인]** 로컬에서 validate와 pytest 모두 통과했고, 화면에서 예시 버튼도 정상 동작합니다. Approve 합니다.

좋은 리뷰는 **무엇이 문제인지 + 왜 + 어떻게 바꾸면 좋을지**를 함께 씁니다. "이상해요"보다 "X일 때 Y가 될 것 같은데 Z는 어떨까요?"가 낫습니다.
