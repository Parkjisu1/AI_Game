var PIXELLAB_API = "https://api.pixellab.ai/v2";
var FIELDMAP_API = "";  // Google Cloud Function URL 여기에 입력
var HEADER_ROW = 2;
var DATA_START = 5;

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("PixelForge")
    .addItem("사이드바 열기", "showSidebar")
    .addSeparator()
    .addItem("선택 행 생성", "generateSelectedRows")
    .addItem("전체 생성 (빈 행만)", "generateAllEmpty")
    .addItem("API Key 설정", "showApiKeyDialog")
    .addSeparator()
    .addItem("시트 진단", "debugSheet")
    .addToUi();
}

function showSidebar() {
  var html = HtmlService.createHtmlOutputFromFile("Sidebar").setTitle("PixelForge").setWidth(350);
  SpreadsheetApp.getUi().showSidebar(html);
}

function showApiKeyDialog() {
  var ui = SpreadsheetApp.getUi();
  var current = PropertiesService.getUserProperties().getProperty("PIXELLAB_API_KEY") || "";
  var result = ui.prompt("API Key", (current ? current.substring(0,8) + "..." : "(없음)"), ui.ButtonSet.OK_CANCEL);
  if (result.getSelectedButton() === ui.Button.OK && result.getResponseText().trim()) {
    PropertiesService.getUserProperties().setProperty("PIXELLAB_API_KEY", result.getResponseText().trim());
    ui.alert("저장됨!");
  }
}

function saveApiKey(key) {
  PropertiesService.getUserProperties().setProperty("PIXELLAB_API_KEY", key);
}

function debugSheet() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var lastCol = sheet.getLastColumn();
  var data = sheet.getRange(1, 1, Math.min(sheet.getLastRow(), 6), lastCol).getValues();
  var result = "시트: " + sheet.getName() + "\n\n";
  for (var r = 0; r < data.length; r++) {
    result += "Row " + (r+1) + ": ";
    for (var c = 0; c < data[r].length; c++) {
      var v = String(data[r][c]).trim();
      if (v) result += "[" + c + "]" + v.substring(0,25) + " | ";
    }
    result += "\n";
  }
  SpreadsheetApp.getUi().alert(result);
}

function getHeaders() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  return sheet.getRange(HEADER_ROW, 1, 1, sheet.getLastColumn()).getValues()[0];
}

function col(headers, name) {
  for (var i = 0; i < headers.length; i++) {
    if (String(headers[i]).trim() === name) return i;
  }
  return -1;
}

// ── designer_note → 상세 프롬프트 ──
function noteToPrompt(note, numColors) {
  if (!note) return "colorful pixel art game level board, bright vivid colors, clean blocks";
  note = String(note);

  // [Motif] 추출
  var motifMatch = note.match(/\[Motif\]\s*(?:구상|추상)?:?\s*([^\[]+)/);
  var motif = motifMatch ? motifMatch[1].trim() : "";

  // [Shape] 추출
  var shapeMatch = note.match(/\[Shape\]\s*([^\[]+)/);
  var shape = shapeMatch ? shapeMatch[1].trim() : "";

  // [Composition] 추출
  var compMatch = note.match(/\[Composition\]\s*([^\[]+)/);
  var comp = compMatch ? compMatch[1].trim() : "";

  // [Pattern] 추출
  var patternMatch = note.match(/\[Pattern\]\s*([^\[]+)/);
  var pattern = patternMatch ? patternMatch[1].trim() : "";

  // 한국어 → 영어
  var map = {
    "고양이 얼굴":"cute cat face","고양이":"cat","물고기":"fish swimming",
    "해 ":"bright sun ","나비":"butterfly with spread wings",
    "음표":"music note","격자":"grid pattern","줄무늬":"colorful stripes",
    "기하학 패턴":"geometric pattern","기하학":"geometric","체커":"checkerboard",
    "소용돌이":"spiral swirl","타일":"repeating tile","꽃":"flower",
    "좌우대칭":"left-right symmetrical","4방향대칭":"4-way symmetrical",
    "원형":"circular round shape","하트":"heart shape",
    "계단":"staircase diagonal steps","삼각형":"triangle",
    "화살표":"arrow pointing","꽉찬 사각형":"filled rectangle",
    "L자":"L-shaped block","벌":"cute bee","곰":"cute bear",
    "별":"shining star","눈사람":"snowman","펭귄":"penguin",
    "강아지":"puppy dog","토끼":"rabbit","당근":"orange carrot",
    "버섯":"red mushroom","호박":"orange pumpkin",
    "그라데이션":"gradient","인접":"adjacent",
    "외곽 테두리 강조":"bold border frame","외곽":"outer border",
    "중심":"center","동심원":"concentric circles",
    "분산":"scattered distributed","유닛 타일링":"unit tiling",
    "단색블록":"solid color blocks","체커보드":"checkerboard",
    "상하대칭":"top-bottom symmetrical","대각선":"diagonal",
  };

  function translate(text) {
    var result = text;
    var keys = Object.keys(map);
    for (var i = 0; i < keys.length; i++) {
      result = result.replace(new RegExp(keys[i], "g"), map[keys[i]]);
    }
    result = result.replace(/휴식\.?|하드\.?|도입\.?/g, "").replace(/\s+/g, " ").trim();
    return result;
  }

  var parts = [];

  // 모티프 (메인 주제)
  var motifEn = translate(motif);
  if (motifEn) parts.push(motifEn);

  // 형태
  var shapeEn = translate(shape);
  if (shapeEn) parts.push(shapeEn);

  // 구성
  var compEn = translate(comp);
  if (compEn) parts.push(compEn);

  // 색상 수 반영
  var colorDesc = "";
  if (numColors) {
    var n = parseInt(numColors);
    if (n <= 3) colorDesc = "simple " + n + " colors";
    else if (n <= 5) colorDesc = "vibrant " + n + " colors red blue green yellow orange";
    else colorDesc = "rich " + n + " colors rainbow palette";
  }
  if (colorDesc) parts.push(colorDesc);

  if (parts.length === 0) parts.push("abstract colorful pattern");

  return parts.join(", ") + ", pixel art game level board, clean bright vivid blocks, top-down view";
}

// ── 인게임 28색 팔레트 (c1~c28) ──
var GAME_PALETTE = {
  1:  [252,106,175],  // #FC6AAF
  2:  [80,232,246],   // #50E8F6
  3:  [137,80,248],   // #8950F8
  4:  [254,213,85],   // #FED555
  5:  [115,254,102],  // #73FE66
  6:  [253,161,76],   // #FDA14C
  7:  [255,255,255],  // #FFFFFF
  8:  [65,65,65],     // #414141
  9:  [110,168,250],  // #6EA8FA
  10: [57,174,46],    // #39AE2E
  11: [252,94,94],    // #FC5E5E
  12: [50,107,248],   // #326BF8
  13: [58,165,139],   // #3AA58B
  14: [231,167,250],  // #E7A7FA
  15: [183,199,251],  // #B7C7FB
  16: [106,74,48],    // #6A4A30
  17: [254,227,169],  // #FEE3A9
  18: [253,183,193],  // #FDB7C1
  19: [158,61,94],    // #9E3D5E
  20: [167,221,148],  // #A7DD94
  21: [89,46,126],    // #592E7E
  22: [220,120,129],  // #DC7881
  23: [217,217,231],  // #D9D9E7
  24: [111,114,127],  // #6F727F
  25: [252,56,165],   // #FC38A5
  26: [253,180,88],   // #FDB458
  27: [137,10,8],     // #890A08
  28: [111,175,177],  // #6FAFB1
};

// color_distribution "c1:105,c2:100,c3:100" → 사용 색상 ID 배열 [1,2,3]
function parseColorDist(dist) {
  if (!dist) return [];
  var ids = [];
  var parts = String(dist).split(",");
  for (var i = 0; i < parts.length; i++) {
    var m = parts[i].trim().match(/c(\d+)/);
    if (m) ids.push(parseInt(m[1]));
  }
  return ids;
}

// 색상 ID 배열 → PixelLab forced_palette 형식 [[r,g,b], ...]
function colorIdsToRgb(ids) {
  var result = [];
  for (var i = 0; i < ids.length; i++) {
    if (GAME_PALETTE[ids[i]]) result.push(GAME_PALETTE[ids[i]]);
  }
  return result;
}

// 색상 ID 배열 → hex 문자열 (프롬프트용)
function colorIdsToHex(ids) {
  var names = {
    1:"pink",2:"cyan",3:"purple",4:"yellow",5:"lime green",6:"orange",
    7:"white",8:"dark gray",9:"sky blue",10:"green",11:"red",12:"blue",
    13:"teal",14:"lavender",15:"light blue",16:"brown",17:"peach",
    18:"light pink",19:"wine",20:"light green",21:"dark purple",
    22:"coral",23:"light gray",24:"gray",25:"magenta",26:"light orange",
    27:"dark red",28:"mint",
  };
  var result = [];
  for (var i = 0; i < ids.length; i++) {
    if (names[ids[i]]) result.push(names[ids[i]]);
  }
  return result.join(", ");
}

// ── API ──
function getApiKey() {
  var key = PropertiesService.getUserProperties().getProperty("PIXELLAB_API_KEY");
  if (!key) throw new Error("API Key 없음");
  return key;
}

function getBalance() {
  var resp = UrlFetchApp.fetch(PIXELLAB_API + "/balance", {
    headers: {"Authorization": "Bearer " + getApiKey()}, muteHttpExceptions: true,
  });
  return JSON.parse(resp.getContentText());
}

function callPixelLab(prompt, w, h) {
  var resp = UrlFetchApp.fetch(PIXELLAB_API + "/create-image-pixflux", {
    method: "post", contentType: "application/json",
    headers: {"Authorization": "Bearer " + getApiKey()},
    payload: JSON.stringify({
      description: prompt,
      image_size: {width: Math.min(Math.max(w,32),400), height: Math.min(Math.max(h,32),400)},
      no_background: false,
    }),
    muteHttpExceptions: true,
  });
  if (resp.getResponseCode() !== 200) throw new Error("API " + resp.getResponseCode() + ": " + resp.getContentText().substring(0,100));
  return JSON.parse(resp.getContentText()).image.base64;
}

// ── Drive ──
function getOutputFolder(folderName) {
  var name = folderName || "PixelForge_Output";
  var f = DriveApp.getFoldersByName(name);
  return f.hasNext() ? f.next() : DriveApp.createFolder(name);
}

function saveToDrive(base64, filename, folderName) {
  var folder = getOutputFolder(folderName);
  var clean = base64.replace(/^data:image\/\w+;base64,/, "");
  var blob = Utilities.newBlob(Utilities.base64Decode(clean), "image/png", filename);
  var existing = folder.getFilesByName(filename);
  if (existing.hasNext()) existing.next().setTrashed(true);
  var file = folder.createFile(blob);
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  return { url: file.getUrl(), downloadUrl: "https://drive.google.com/uc?export=download&id=" + file.getId() };
}

function saveJson(data, filename, folderName) {
  var folder = getOutputFolder(folderName);
  var jsonStr = JSON.stringify(data, null, 2);
  var blob = Utilities.newBlob(jsonStr, "application/json", filename);
  var existing = folder.getFilesByName(filename);
  if (existing.hasNext()) existing.next().setTrashed(true);
  var file = folder.createFile(blob);
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  return {
    url: file.getUrl(),
    downloadUrl: "https://drive.google.com/uc?export=download&id=" + file.getId(),
    jsonContent: jsonStr,
  };
}

// ── 사이드바 ──
function getSelectedRowsData() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var sel = sheet.getActiveRange();
  var startRow = sel.getRow();
  var numRows = sel.getNumRows();
  var headers = getHeaders();
  var lastCol = sheet.getLastColumn();

  var levelIdx = col(headers, "level_number");
  var rowsIdx = col(headers, "field_rows");
  var colsIdx = col(headers, "field_columns");
  var noteIdx = col(headers, "designer_note");
  var numColorsIdx = col(headers, "num_colors");

  var results = [];
  for (var r = startRow; r < startRow + numRows; r++) {
    if (r < DATA_START) continue;
    var rowData = sheet.getRange(r, 1, 1, lastCol).getValues()[0];
    var note = noteIdx >= 0 ? String(rowData[noteIdx]) : "";
    var nc = numColorsIdx >= 0 ? rowData[numColorsIdx] : 4;
    results.push({
      row: r,
      level: levelIdx >= 0 ? rowData[levelIdx] : r,
      cols: colsIdx >= 0 ? parseInt(rowData[colsIdx]) || 20 : 20,
      rows: rowsIdx >= 0 ? parseInt(rowData[rowsIdx]) || 20 : 20,
      prompt: noteToPrompt(note, nc),
    });
  }
  return results;
}

function getSelectedRowData() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var row = sheet.getActiveRange().getRow();
  if (row < DATA_START) return null;

  var headers = getHeaders();
  var rowData = sheet.getRange(row, 1, 1, sheet.getLastColumn()).getValues()[0];

  var levelIdx = col(headers, "level_number");
  var rowsIdx = col(headers, "field_rows");
  var colsIdx = col(headers, "field_columns");
  var noteIdx = col(headers, "designer_note");
  var numColorsIdx = col(headers, "num_colors");

  var note = noteIdx >= 0 ? String(rowData[noteIdx]) : "";
  var numColors = numColorsIdx >= 0 ? rowData[numColorsIdx] : 4;

  return {
    row: row,
    level: levelIdx >= 0 ? rowData[levelIdx] : "",
    cols: colsIdx >= 0 ? parseInt(rowData[colsIdx]) || 20 : 20,
    rows: rowsIdx >= 0 ? parseInt(rowData[rowsIdx]) || 20 : 20,
    prompt: noteToPrompt(note, numColors),
    debug: "level@" + levelIdx + " rows@" + rowsIdx + " cols@" + colsIdx + " note@" + noteIdx,
  };
}

// ── PixelLab 이미지 → [FieldMap] 텍스트 변환 ──
// base64 이미지를 cols x rows 그리드로 축소 → 색상 ID 매핑
// 형식: "01 02 .. ..\n03 01 02 .."  (1-based color, ".."=빈셀)
function imageToFieldMap(base64Data, cols, rows, numColors, colorIds) {
  // Cloud Function으로 이미지 → FieldMap 변환
  if (!FIELDMAP_API) {
    Logger.log("FIELDMAP_API URL 미설정 — 패턴 기반 생성");
    return fallbackFieldMap(cols, rows, colorIds);
  }

  var cleanB64 = base64Data.replace(/^data:image\/\w+;base64,/, "");

  var resp = UrlFetchApp.fetch(FIELDMAP_API, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({
      image_base64: cleanB64,
      cols: cols,
      rows: rows,
      allowed_colors: colorIds && colorIds.length > 0 ? colorIds : null,
    }),
    muteHttpExceptions: true,
  });

  if (resp.getResponseCode() === 200) {
    var data = JSON.parse(resp.getContentText());
    return data.fieldmap;
  }

  Logger.log("FieldMap API error: " + resp.getContentText().substring(0, 200));
  return fallbackFieldMap(cols, rows, colorIds);
}

// API 실패 시 fallback: 색상 ID로 단순 패턴
function fallbackFieldMap(cols, rows, colorIds) {
  var ids = colorIds && colorIds.length > 0 ? colorIds : [1,2,3,4,5];
  var lines = [];
  for (var y = 0; y < rows; y++) {
    var line = [];
    for (var x = 0; x < cols; x++) {
      var colorId = ids[(x + y) % ids.length]; // 대각선 패턴
      line.push(String(colorId).padStart(2, "0"));
    }
    lines.push(line.join(" "));
  }
  return lines.join("\n");
}

function generateFromSidebar(rowIndex, customPrompt, folderName) {
  var headers = getHeaders();
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var lastCol = sheet.getLastColumn();
  var rowData = sheet.getRange(rowIndex, 1, 1, lastCol).getValues()[0];

  // 모든 컬럼 읽기
  function g(name) { var i = col(headers, name); return i >= 0 ? rowData[i] : null; }
  function gi(name, def) { var v = g(name); return v !== null ? (parseInt(v) || def) : def; }
  function gf(name, def) { var v = g(name); return v !== null ? (parseFloat(v) || def) : def; }
  function gs(name, def) { var v = g(name); return v !== null ? String(v) : (def || ""); }

  var levelNum = gi("level_number", rowIndex);
  var cols = gi("field_columns", 20);
  var rows = gi("field_rows", 20);
  var numColors = gi("num_colors", 4);
  var prompt = customPrompt || "pixel art pattern";
  var filename = "level_" + String(levelNum).padStart(3, "0") + ".png";
  var jsonFilename = filename.replace(".png", ".json");

  // 색상 팔레트 추출 (color_distribution 기반)
  var colorDist = gs("color_distribution", "");
  var colorIds = parseColorDist(colorDist);
  if (colorIds.length === 0) {
    // color_distribution 없으면 num_colors 기반 기본 팔레트
    for (var ci = 1; ci <= numColors; ci++) colorIds.push(ci);
  }
  var palette = colorIdsToRgb(colorIds);
  var colorNames = colorIdsToHex(colorIds);

  // 프롬프트에 색상 정보 추가
  if (colorNames && prompt.indexOf(colorNames) < 0) {
    prompt += ", using only " + colorNames + " colors";
  }

  // 1. PixelLab API 호출
  // 128px로 생성 (품질 확보) — FieldMap 변환 시 cols x rows로 리사이즈
  var apiSize = 128;
  var imgB64 = callPixelLab(prompt, apiSize, apiSize);

  // 2. 이미지 Drive 저장
  var imgResult = saveToDrive(imgB64, filename, folderName);

  // 3. FieldMap 생성 (color_distribution의 실제 색상 ID 사용)
  var fieldMap = imageToFieldMap(imgB64, cols, rows, numColors, colorIds);

  // 4. Unity importer 호환 JSON 생성 (시트의 모든 컬럼 포함)
  var designerNote = gs("designer_note", "");
  // designer_note에 [FieldMap] 추가
  var noteWithFieldMap = designerNote;
  // 기존 [FieldMap] 제거 후 새로 추가
  var fmIdx = noteWithFieldMap.indexOf("[FieldMap]");
  if (fmIdx >= 0) noteWithFieldMap = noteWithFieldMap.substring(0, fmIdx).trim();
  noteWithFieldMap += "\n[FieldMap]\n" + fieldMap;

  var levelJson = {
    level_number: levelNum,
    level_id: gs("level_id", "BF_" + String(levelNum).padStart(3, "0")),
    pkg: gi("pkg", 1),
    pos: gi("pos", 1),
    chapter: gi("chapter", 1),
    purpose_type: gs("purpose_type", "노말"),
    target_cr: gi("target_cr", 60),
    target_attempts: gf("target_attempts", 1.8),
    num_colors: numColors,
    color_distribution: gs("color_distribution", ""),
    field_rows: rows,
    field_columns: cols,
    total_cells: gi("total_cells", rows * cols),
    rail_capacity: gi("rail_capacity", 160),
    rail_capacity_tier: gs("rail_capacity_tier", "701+"),
    queue_columns: gi("queue_columns", 2),
    queue_rows: gi("queue_rows", 20),
    gimmick_hidden: gi("gimmick_hidden", 0),
    gimmick_chain: gi("gimmick_chain", 0),
    gimmick_pinata: gi("gimmick_pinata", 0),
    gimmick_spawner_t: gi("gimmick_spawner_t", 0),
    gimmick_pin: gi("gimmick_pin", 0),
    gimmick_lock_key: gi("gimmick_lock_key", 0),
    gimmick_surprise: gi("gimmick_surprise", 0),
    gimmick_wall: gi("gimmick_wall", 0),
    gimmick_spawner_o: gi("gimmick_spawner_o", 0),
    gimmick_pinata_box: gi("gimmick_pinata_box", 0),
    gimmick_ice: gi("gimmick_ice", 0),
    gimmick_frozen_dart: gi("gimmick_frozen_dart", 0),
    gimmick_curtain: gi("gimmick_curtain", 0),
    total_darts: gi("total_darts", 0),
    dart_capacity_range: gs("dart_capacity_range", ""),
    emotion_curve: gs("emotion_curve", ""),
    designer_note: noteWithFieldMap,
    pixel_art_source: filename,
  };

  var jsonResult = saveJson(levelJson, jsonFilename, folderName);

  return {
    imgUrl: imgResult.url, imgDownloadUrl: imgResult.downloadUrl,
    jsonUrl: jsonResult.url, jsonDownloadUrl: jsonResult.downloadUrl,
    jsonContent: jsonResult.jsonContent,
    filename: filename, jsonFilename: jsonFilename, prompt: prompt,
  };
}

function generateSelectedRows(folderName) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var sel = sheet.getActiveRange();
  var headers = getHeaders();
  var numColorsIdx = col(headers, "num_colors");
  var results = [];
  for (var i = sel.getRow(); i < sel.getRow() + sel.getNumRows(); i++) {
    if (i < DATA_START) continue;
    try {
      var rowData = sheet.getRange(i, 1, 1, sheet.getLastColumn()).getValues()[0];
      var noteIdx = col(headers, "designer_note");
      var note = noteIdx >= 0 ? String(rowData[noteIdx]) : "";
      var nc = numColorsIdx >= 0 ? rowData[numColorsIdx] : 4;
      generateFromSidebar(i, noteToPrompt(note, nc), folderName);
      results.push("OK Row " + i);
    } catch (e) { results.push("FAIL Row " + i + ": " + e.message); }
  }
  SpreadsheetApp.getUi().alert(results.join("\n"));
}

function generateAllEmpty(folderName) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var headers = getHeaders();
  var srcIdx = col(headers, "pixel_art_source");
  var noteIdx = col(headers, "designer_note");
  var numColorsIdx = col(headers, "num_colors");
  var count = 0;
  for (var i = DATA_START; i <= sheet.getLastRow(); i++) {
    if (srcIdx >= 0) {
      var val = sheet.getRange(i, srcIdx + 1).getValue();
      if (val && String(val).trim()) continue;
    }
    try {
      var rowData = sheet.getRange(i, 1, 1, sheet.getLastColumn()).getValues()[0];
      var note = noteIdx >= 0 ? String(rowData[noteIdx]) : "";
      var nc = numColorsIdx >= 0 ? rowData[numColorsIdx] : 4;
      generateFromSidebar(i, noteToPrompt(note, nc), folderName);
      count++;
    } catch (e) { Logger.log("Row " + i + ": " + e.message); }
    Utilities.sleep(1000);
  }
  SpreadsheetApp.getUi().alert(count + "개 완료");
}
