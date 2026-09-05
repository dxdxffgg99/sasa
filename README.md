# sasa

영재원에서 반에 있는 천재 둘 납치해서 만든 리듬게임

## 실행

```bash
pip install -r requirements.txt
python app.py              # 곡 선택 화면
python app.py R.dx         # 이 채보로 바로 시작
```

곡 선택 화면에서 `↑` `↓` 로 고르고 `ENTER` 로 시작, `ESC` 로 종료.
플레이 중 `ESC` 를 누르면 곡 선택으로 돌아온다. 노트 키는 `Z` `X` `.` `/` 네 개.

곡이 끝나면 결과 화면에서 판정별 개수와 정확도, 그리고 내 입력 오차를 바탕으로
계산한 추천 `offset` 값을 보여준다. 노트가 계속 이르게 느껴지면 그 값을 채보의
`offset:` 에 적으면 된다.

## .dx — 채보 포맷

`app.py` 는 실행 파일과 같은 폴더의 `.dx` 파일을 전부 찾아 목록에 올린다.
`.dx` 는 UTF-8 텍스트고 헤더와 노트 두 부분으로 나뉜다.

```
title: Pixelation
artist: Sound Souler
audio: pixelation.mp3
bpm: 129.2
offset: 0
lead_in: 2000
difficulty: NORMAL
level: 6
beats_per_measure: 4

[notes]
# when      lanes   hold
2116        1
4:1         2,4
4:1.5       3       1b
```

### 헤더

| 키 | 뜻 | 기본값 |
|---|---|---|
| `title` | 곡 선택 화면에 뜨는 이름 | 파일 이름 |
| `artist` | 아티스트 | 없음 |
| `audio` | 음원 파일. 채보 파일 기준 상대 경로 | 없음 (무음 플레이) |
| `bpm` | 템포. `measure:beat` 표기를 쓰려면 필수 | 120 |
| `offset` | 판정 보정 ms. 노트가 늦게 오면 올린다 | 0 |
| `lead_in` | 첫 노트 전 무음 구간 ms | 2000 |
| `difficulty` | `EASY` / `NORMAL` / `HARD` 같은 라벨 | 없음 |
| `level` | 난이도 숫자. 0이면 표시 안 함 | 0 |
| `beats_per_measure` | 한 마디의 박 수 | 4 |

없는 키를 쓰면 오타를 조용히 넘기지 않고 줄 번호와 함께 에러를 낸다.

### 노트

한 줄에 노트 하나, 열은 최대 세 개다.

- **when** — 시간. 두 가지로 쓸 수 있다.
  - `2116` → 곡이 시작하고 2116 ms. **`lead_in` 은 빼고 센다**. 무음 구간 길이가
    바뀌어도 채보를 고칠 필요가 없다.
  - `4:1.5` → 4번째 마디의 1.5번째 박. 마디와 박 둘 다 1부터 세니까 `1:1` 이 곡의
    첫 박이다. `bpm` 과 `beats_per_measure` 로 ms 로 환산된다.
- **lanes** — `1` ~ `4`. 콤마로 이으면 동시치기다: `2,4`
- **hold** — 있으면 롱노트. `450` 은 밀리초, `1b` 는 한 박, `1.5b` 는 한 박 반.
  비우거나 `-` 를 쓰면 일반 노트.

`#` 뒤는 주석이고 빈 줄은 마음대로 넣어도 된다. 노트 순서는 상관없다 — 읽을 때
시간순으로 정렬한다.

### 도구

```bash
python make_chart.py song.mp3                      # song.dx 자동 생성
python make_chart.py song.mp3 -d hard --title "곡 이름" --level 9
python dx.py chart.dx                              # 문법 검사
python dx.py old_chart.json                        # 예전 json 채보를 .dx 로 변환
```

# FONT
> **[경기천년제목체](https://www.gg.go.kr/contents/contents.do?ciIdx=679&menuId=2457)**  
> 경기도 서체는 누구나 무료로 다운로드 받아 자유롭게 사용할 수 있습니다.
> 영상, 인쇄, 웹 등 다양한 매체에 자유롭게 사용이 가능하며, 특별한 허가 절차 없이 사용할 수 있습니다.
> 다만, 경기도 서체를 유료로 양도하거나 판매하는 등 상업적 행위는 금지하고 있습니다.
