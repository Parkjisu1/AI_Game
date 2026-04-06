/**
 * PixelForge — Google Sheets Extension
 * =====================================
 * 레벨 디자인 시트에서 PixelLab API로 픽셀아트 보드 자동 생성.
 *
 * 시트 컬럼: field_rows, field_columns, num_colors, designer_note, pixel_art_source
 * → PixelLab API → 보드 이미지 + JSON → Google Drive 저장
 */

// ── 설정 ──
const PIXELLAB_API = "https://api.pixellab.ai/v2";
const DRIVE_FOLDER_NAME = "PixelForge_Output";

// 인게임 15색 팔레트 (RGB)
const PALETTE_CORE = [
  [252,94,94],[253,161,76],[254,213,85],[115,254,102],[57,174,46],
  [80,232,246],[50,107,248],[137,80,248],[252,106,175],[252,56,165],
  [255,255,255],[65,65,65],[111,114,127],[106,74,48],[254,227,169],
];

// ═══════════════════════════════════════════════════
//  메뉴 & 사이드바
// ═══════════════════════════════════════════════════

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("🎨 PixelForge")
    .addItem("사이드바 열기", "showSidebar")
    .addSeparator()
    .addItem("선택 행 생성", "generateSelectedRows")
    .addItem("전체 생성 (빈 행만)", "generateAllEmpty")
    .addItem("⚙️ API Key 설정", "showApiKeyDialog")
    .addToUi();
}

function showSidebar() {
  const html = HtmlService.createHtmlOutputFromFile("Sidebar")
    .setTitle("PixelForge")
    .setWidth(350);
  SpreadsheetApp.getUi().showSidebar(html);
}

function showApiKeyDialog() {
  const ui = SpreadsheetApp.getUi();
  const current = PropertiesService.getUserProperties().getProperty("PIXELLAB_API_KEY") || "";
  const result = ui.prompt(
    "PixelLab API Key 설정",
    `현재: ${current ? current.substring(0,8) + "..." : "(없음)"}\n새 키 입력:`,
    ui.ButtonSet.OK_CANCEL
  );
  if (result.getSelectedButton() === ui.Button.OK) {
    const key = result.getResponseText().trim();
    if (key) {
      PropertiesService.getUserProperties().setProperty("PIXELLAB_API_KEY", key);
      ui.alert("API Key 저장됨!");
    }
  }
}

// ═══════════════════════════════════════════════════
//  핵심: designer_note → 프롬프트 변환
// ═══════════════════════════════════════════════════

function noteToPrompt(designerNote) {
  if (!designerNote) return "pixel art pattern";

  // [Motif] 추출
  const motifMatch = designerNote.match(/\[Motif\]\s*(?:구상|추상)?:?\s*([^\[]+)/);
  const motif = motifMatch ? motifMatch[1].trim() : "";

  // [Shape] 추출
  const shapeMatch = designerNote.match(/\[Shape\]\s*([^\[]+)/);
  const shape = shapeMatch ? shapeMatch[1].trim() : "";

  // [Composition] 추출
  const compMatch = designerNote.match(/\[Composition\]\s*([^\[]+)/);
  const comp = compMatch ? compMatch[1].trim() : "";

  // 한국어 → 영어 매핑
  const koToEn = {
    "고양이 얼굴": "cute cat face",
    "물고기": "fish",
    "해": "sun",
    "나비": "butterfly",
    "음표": "music note",
    "격자": "grid pattern",
    "줄무늬": "stripes",
    "기하학 패턴": "geometric pattern",
    "체커": "checker pattern",
    "소용돌이": "spiral",
    "타일": "tile pattern",
    "좌우대칭": "symmetrical",
    "4방향대칭": "four-way symmetrical",
    "원형": "circular",
    "하트": "heart shape",
    "계단": "staircase",
    "삼각형": "triangle",
    "화살표": "arrow",
    "꽉찬 사각형": "filled square",
    "L자": "L-shape",
  };

  let prompt = motif;
  for (const [ko, en] of Object.entries(koToEn)) {
    prompt = prompt.replace(ko, en);
  }

  // shape 추가
  let shapeEn = shape;
  for (const [ko, en] of Object.entries(koToEn)) {
    shapeEn = shapeEn.replace(ko, en);
  }

  if (shapeEn && !prompt.includes(shapeEn)) {
    prompt += ", " + shapeEn;
  }

  // 클린업
  prompt = prompt.replace(/휴식\.?|하드\.?|도입\.?/g, "").trim();
  prompt = prompt.replace(/\s+/g, " ").trim();

  if (!prompt) prompt = "abstract pixel art pattern";

  return prompt + ", pixel art, colorful blocks";
}

// ═══════════════════════════════════════════════════
//  PixelLab API 호출
// ═══════════════════════════════════════════════════

function getApiKey() {
  const key = PropertiesService.getUserProperties().getProperty("PIXELLAB_API_KEY");
  if (!key) throw new Error("API Key가 설정되지 않았습니다. 메뉴 > PixelForge > API Key 설정");
  return key;
}

function callPixelLab(prompt, width, height) {
  const key = getApiKey();

  // API 크기 제한 (최대 400x400)
  const apiW = Math.min(Math.max(width, 32), 400);
  const apiH = Math.min(Math.max(height, 32), 400);

  const payload = {
    description: prompt,
    image_size: { width: apiW, height: apiH },
    no_background: false,
  };

  const options = {
    method: "post",
    contentType: "application/json",
    headers: { Authorization: "Bearer " + key },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  };

  const resp = UrlFetchApp.fetch(PIXELLAB_API + "/create-image-pixflux", options);

  if (resp.getResponseCode() !== 200) {
    throw new Error("API 에러: " + resp.getContentText().substring(0, 200));
  }

  const data = JSON.parse(resp.getContentText());
  return data.image.base64;
}

// ═══════════════════════════════════════════════════
//  이미지 → 팔레트 매핑 → JSON 그리드
// ═══════════════════════════════════════════════════

function imageToGrid(base64Data, cols, rows, numColors) {
  // base64 → Blob → 원본 이미지 데이터
  // Apps Script에서는 Canvas가 없으므로 간단한 리사이즈 불가
  // → 이미지를 그대로 Drive에 저장하고, 그리드 데이터는 별도 생성

  // 팔레트에서 numColors만큼 선택
  const palette = PALETTE_CORE.slice(0, Math.min(numColors + 2, PALETTE_CORE.length));

  return {
    cols: cols,
    rows: rows,
    num_colors: numColors,
    palette: palette,
    // 실제 그리드 데이터는 로컬 Python에서 생성하거나
    // 이미지 자체를 레벨 데이터로 사용
  };
}

// ═══════════════════════════════════════════════════
//  Google Drive 저장
// ═══════════════════════════════════════════════════

function getOutputFolder() {
  const folders = DriveApp.getFoldersByName(DRIVE_FOLDER_NAME);
  if (folders.hasNext()) return folders.next();
  return DriveApp.createFolder(DRIVE_FOLDER_NAME);
}

function saveImageToDrive(base64Data, filename) {
  const folder = getOutputFolder();

  // base64에서 data URI 제거
  const cleanB64 = base64Data.replace(/^data:image\/\w+;base64,/, "");
  const blob = Utilities.newBlob(Utilities.base64Decode(cleanB64), "image/png", filename);

  // 기존 파일 덮어쓰기
  const existing = folder.getFilesByName(filename);
  if (existing.hasNext()) existing.next().setTrashed(true);

  const file = folder.createFile(blob);
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  return file.getUrl();
}

function saveJsonToDrive(jsonData, filename) {
  const folder = getOutputFolder();
  const blob = Utilities.newBlob(JSON.stringify(jsonData, null, 2), "application/json", filename);

  const existing = folder.getFilesByName(filename);
  if (existing.hasNext()) existing.next().setTrashed(true);

  const file = folder.createFile(blob);
  return file.getUrl();
}

// ═══════════════════════════════════════════════════
//  행 단위 생성
// ═══════════════════════════════════════════════════

function generateRow(rowIndex) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const rowData = sheet.getRange(rowIndex, 1, 1, sheet.getLastColumn()).getValues()[0];

  // 컬럼 인덱스 찾기
  const colIdx = (name) => headers.indexOf(name);

  const cols = parseInt(rowData[colIdx("field_columns")]) || 20;
  const rows = parseInt(rowData[colIdx("field_rows")]) || 20;
  const numColors = parseInt(rowData[colIdx("num_colors")]) || 4;
  const designerNote = rowData[colIdx("designer_note")] || "";
  const levelNum = rowData[colIdx("level_number")] || rowIndex;
  const filename = rowData[colIdx("pixel_art_source")] || `level_${String(levelNum).padStart(3,"0")}.png`;

  // 프롬프트 생성
  const prompt = noteToPrompt(designerNote);

  // API 호출 (크기 = 셀 수에 비례, 최대 128)
  const apiSize = Math.min(128, Math.max(32, Math.max(cols, rows) * 2));

  Logger.log(`Row ${rowIndex}: ${cols}x${rows}, ${numColors}색, prompt="${prompt}"`);

  const imgBase64 = callPixelLab(prompt, apiSize, apiSize);

  // Drive에 저장
  const imgUrl = saveImageToDrive(imgBase64, filename);
  const jsonFilename = filename.replace(".png", ".json");
  const gridData = {
    level_number: levelNum,
    cols: cols,
    rows: rows,
    num_colors: numColors,
    prompt: prompt,
    designer_note: designerNote,
  };
  const jsonUrl = saveJsonToDrive(gridData, jsonFilename);

  // 시트에 결과 기록 (pixel_art_source 컬럼 옆에)
  const srcColIdx = colIdx("pixel_art_source");
  if (srcColIdx >= 0) {
    sheet.getRange(rowIndex, srcColIdx + 1).setValue(filename);
  }

  return {
    row: rowIndex,
    level: levelNum,
    prompt: prompt,
    cols: cols,
    rows: rows,
    imgUrl: imgUrl,
    jsonUrl: jsonUrl,
  };
}

// ═══════════════════════════════════════════════════
//  메뉴 액션
// ═══════════════════════════════════════════════════

function generateSelectedRows() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const selection = sheet.getActiveRange();
  const startRow = selection.getRow();
  const numRows = selection.getNumRows();

  const results = [];
  for (let i = startRow; i < startRow + numRows; i++) {
    if (i <= 1) continue; // 헤더 스킵
    try {
      const result = generateRow(i);
      results.push(`✅ Level ${result.level}: ${result.prompt.substring(0,40)}...`);
    } catch (e) {
      results.push(`❌ Row ${i}: ${e.message}`);
    }
  }

  SpreadsheetApp.getUi().alert("생성 완료!\n\n" + results.join("\n"));
}

function generateAllEmpty() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const lastRow = sheet.getLastRow();

  const results = [];
  let count = 0;

  for (let i = 2; i <= lastRow; i++) {
    // pixel_art_source 컬럼이 비어있는 행만
    const srcIdx = headers.indexOf("pixel_art_source");
    const val = sheet.getRange(i, srcIdx + 1).getValue();

    if (val && String(val).trim() !== "") {
      continue; // 이미 생성됨
    }

    try {
      const result = generateRow(i);
      results.push(`✅ Level ${result.level}`);
      count++;
    } catch (e) {
      results.push(`❌ Row ${i}: ${e.message}`);
    }

    // API rate limit 방지
    Utilities.sleep(1000);
  }

  SpreadsheetApp.getUi().alert(`${count}개 레벨 생성 완료!\n\n` + results.join("\n"));
}

// ═══════════════════════════════════════════════════
//  사이드바에서 호출하는 함수들
// ═══════════════════════════════════════════════════

function saveApiKey(key) {
  PropertiesService.getUserProperties().setProperty("PIXELLAB_API_KEY", key);
}

function getBalance() {
  const key = getApiKey();
  const resp = UrlFetchApp.fetch(PIXELLAB_API + "/balance", {
    headers: { Authorization: "Bearer " + key },
    muteHttpExceptions: true,
  });
  return JSON.parse(resp.getContentText());
}

function getSelectedRowData() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const selection = sheet.getActiveRange();
  const row = selection.getRow();
  if (row <= 1) return null;

  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const rowData = sheet.getRange(row, 1, 1, sheet.getLastColumn()).getValues()[0];

  const colIdx = (name) => headers.indexOf(name);

  const designerNote = rowData[colIdx("designer_note")] || "";

  return {
    row: row,
    level: rowData[colIdx("level_number")],
    cols: parseInt(rowData[colIdx("field_columns")]) || 20,
    rows: parseInt(rowData[colIdx("field_rows")]) || 20,
    numColors: parseInt(rowData[colIdx("num_colors")]) || 4,
    designerNote: designerNote,
    prompt: noteToPrompt(designerNote),
    filename: rowData[colIdx("pixel_art_source")] || "",
  };
}

function generateFromSidebar(rowIndex, customPrompt) {
  if (customPrompt) {
    // 사이드바에서 프롬프트 수정 후 생성
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    const rowData = sheet.getRange(rowIndex, 1, 1, sheet.getLastColumn()).getValues()[0];
    const colIdx = (name) => headers.indexOf(name);

    const cols = parseInt(rowData[colIdx("field_columns")]) || 20;
    const rows = parseInt(rowData[colIdx("field_rows")]) || 20;
    const numColors = parseInt(rowData[colIdx("num_colors")]) || 4;
    const levelNum = rowData[colIdx("level_number")] || rowIndex;
    const filename = `level_${String(levelNum).padStart(3,"0")}.png`;

    const apiSize = Math.min(128, Math.max(32, Math.max(cols, rows) * 2));
    const imgBase64 = callPixelLab(customPrompt, apiSize, apiSize);
    const imgUrl = saveImageToDrive(imgBase64, filename);

    const jsonData = { level_number: levelNum, cols, rows, num_colors: numColors, prompt: customPrompt };
    const jsonUrl = saveJsonToDrive(jsonData, filename.replace(".png", ".json"));

    return { imgUrl, jsonUrl, prompt: customPrompt };
  }

  return generateRow(rowIndex);
}
