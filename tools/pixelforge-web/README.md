# PixelForge Web

레벨 데이터 입력 → AI 픽셀 아트 이미지 생성 → Unity Importer가 읽는 JSON 빌드까지 한 번에 처리하는 Next.js 16 기반 웹 도구.

## 주요 페이지

| 경로 | 용도 |
|---|---|
| `/` | 대시보드 |
| `/levels` | 레벨 데이터 입력/편집 (CSV 가져오기 지원) |
| `/generate` | PixelLab API 호출하여 픽셀 아트 생성 |
| `/gallery` | 생성된 이미지 갤러리 + JSON 다운로드 |
| `/json-vault` | **레벨별 JSON inline 미리보기 + 복사/공유/다운로드** (모바일 친화) |
| `/tasks` | 작업 보드 |

## 로컬 실행

```bash
cp .env.example .env.local
# .env.local에 MONGODB_URI 채우기
npm install
npm run dev
```

[http://localhost:3000](http://localhost:3000) 접속.

## Vercel 배포

1. **GitHub 푸시**: `tools/pixelforge-web` 디렉터리를 별도 저장소 또는 monorepo로 push
2. **Vercel 프로젝트 생성**: vercel.com → "Import Project" → 저장소 선택
   - **Root Directory**: monorepo면 `tools/pixelforge-web` 지정
   - **Framework Preset**: Next.js (자동 감지)
3. **환경변수 설정** (Vercel 대시보드 → Settings → Environment Variables):
   | Key | 값 |
   |---|---|
   | `MONGODB_URI` | MongoDB Atlas 연결 문자열 |
   | `MONGODB_DB` | `aigame` (또는 사용 중인 DB명) |
4. **MongoDB Atlas Network Access**: Vercel은 동적 IP를 사용하므로 `0.0.0.0/0` 허용 필요 (또는 Vercel 전용 IP 화이트리스트)
5. **Deploy** 버튼 클릭 → 빌드 완료 후 `https://your-project.vercel.app` 접속

### 모바일 사용 흐름
1. 폰에서 배포된 URL 접속 → PixelLab API Key를 폰의 localStorage에 저장
2. 레벨 데이터 입력 또는 이미지 생성
3. **JSON 보관함** 페이지에서 레벨별 JSON 확인 → 복사·공유 버튼으로 메모/메일/메신저로 보내기
4. PC에서 동일 URL 접속 → 같은 MongoDB 데이터를 보고 JSON 다운로드 → Unity Import

> **Tip**: PixelLab API Key는 클라이언트 localStorage에 저장되므로 PC와 폰을 따로 설정해야 함. 둘 다 동일한 MongoDB Atlas를 바라보므로 레벨 데이터는 자동으로 공유됨.

## 빌드 검증 (배포 전 로컬)

```bash
npm run build
npm start
```

## 기술 스택
- Next.js 16.2.2 (App Router)
- React 19
- Tailwind CSS 4
- MongoDB Atlas (Node driver 7)
- PixelLab API (이미지 생성)
