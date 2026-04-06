var PIXELLAB_API = "https://api.pixellab.ai/v2";
var HEADER_ROW = 2;
var DATA_START = 5;

// 인게임 28색 팔레트
var GAME_PALETTE = {
  1:[252,106,175],2:[80,232,246],3:[137,80,248],4:[254,213,85],5:[115,254,102],
  6:[253,161,76],7:[255,255,255],8:[65,65,65],9:[110,168,250],10:[57,174,46],
  11:[252,94,94],12:[50,107,248],13:[58,165,139],14:[231,167,250],15:[183,199,251],
  16:[106,74,48],17:[254,227,169],18:[253,183,193],19:[158,61,94],20:[167,221,148],
  21:[89,46,126],22:[220,120,129],23:[217,217,231],24:[111,114,127],25:[252,56,165],
  26:[253,180,88],27:[137,10,8],28:[111,175,177],
};
var PAL_KEYS = Object.keys(GAME_PALETTE).map(Number);
var PAL_RGB = PAL_KEYS.map(function(k) { return GAME_PALETTE[k]; });

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

function getSavedApiKey() {
  return PropertiesService.getUserProperties().getProperty("PIXELLAB_API_KEY") || "";
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

// ═══════════════════════════════════════
//  PNG → 픽셀 RGB 추출 (Apps Script 전용)
// ═══════════════════════════════════════

function pngToPixels(base64Data, targetW, targetH) {
  // PNG base64 → Google Drive에 임시 저장 → Sheets에 삽입 → 픽셀 읽기
  // 대안: PNG를 BMP로 변환하여 raw 픽셀 접근
  //
  // 가장 실용적 방법: PixelLab에 정확한 크기로 요청 후,
  // Drive API 썸네일로 색상 샘플링

  var cleanB64 = base64Data.replace(/^data:image\/\w+;base64,/, "");
  var bytes = Utilities.base64Decode(cleanB64);
  var blob = Utilities.newBlob(bytes, "image/png", "temp_pixel.png");

  // PNG → Drive 임시 저장
  var file = DriveApp.createFile(blob);
  var fileId = file.getId();

  // Drive Advanced API로 썸네일 가져오기 시도
  // 안 되면 fallback: 이미지 자체를 분석

  try {
    // Drive REST API로 이미지 다운로드 (원본 bytes)
    var url = "https://www.googleapis.com/drive/v3/files/" + fileId + "?alt=media";
    var resp = UrlFetchApp.fetch(url, {
      headers: { "Authorization": "Bearer " + ScriptApp.getOAuthToken() },
    });
    var pngBytes = resp.getContent(); // byte array

    // PNG 파싱: IHDR에서 크기, IDAT에서 픽셀
    var pixels = decodePngPixels(pngBytes);

    file.setTrashed(true);

    if (pixels && pixels.length > 0) {
      return resamplePixels(pixels, targetW, targetH);
    }
  } catch (e) {
    Logger.log("PNG decode error: " + e.message);
  }

  file.setTrashed(true);
  return null;
}

function decodePngPixels(pngBytes) {
  // PNG 구조: 8바이트 시그니처 → 청크(IHDR, IDAT, IEND)
  // IDAT: zlib 압축 → Utilities.ungzip 으로 해제 불가 (gzip != zlib)
  // 대신: zlib 데이터를 gzip으로 래핑하여 해제

  var bytes = pngBytes;
  if (bytes[0] !== 0x89 || bytes[1] !== 0x50) return null; // PNG 시그니처 확인

  var pos = 8; // 시그니처 이후
  var width = 0, height = 0, bitDepth = 0, colorType = 0;
  var idatChunks = [];

  while (pos < bytes.length) {
    var len = (bytes[pos] << 24) | (bytes[pos+1] << 16) | (bytes[pos+2] << 8) | bytes[pos+3];
    var type = String.fromCharCode(bytes[pos+4], bytes[pos+5], bytes[pos+6], bytes[pos+7]);

    if (type === "IHDR") {
      width = (bytes[pos+8] << 24) | (bytes[pos+9] << 16) | (bytes[pos+10] << 8) | bytes[pos+11];
      height = (bytes[pos+12] << 24) | (bytes[pos+13] << 16) | (bytes[pos+14] << 8) | bytes[pos+15];
      bitDepth = bytes[pos+16];
      colorType = bytes[pos+17];
    } else if (type === "IDAT") {
      for (var i = 0; i < len; i++) {
        idatChunks.push(bytes[pos + 8 + i]);
      }
    } else if (type === "IEND") {
      break;
    }
    pos += 12 + len; // 4(len) + 4(type) + len(data) + 4(crc)
  }

  if (width === 0 || idatChunks.length === 0) return null;

  // zlib → gzip 래핑: zlib = [CMF, FLG] + DEFLATE + [ADLER32]
  // gzip = [1f 8b 08 00 00 00 00 00 00 03] + DEFLATE + [CRC32, SIZE]
  var deflateData = idatChunks.slice(2, idatChunks.length - 4); // zlib 헤더(2) + 체크섬(4) 제거

  // gzip 헤더
  var gzipHeader = [0x1f, 0x8b, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03];
  // gzip 푸터 (CRC32=0, SIZE=0 — 더미, ungzip이 무시함)
  var gzipFooter = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00];

  var gzipBytes = gzipHeader.concat(deflateData).concat(gzipFooter);
  var gzipBlob = Utilities.newBlob(gzipBytes, "application/x-gzip");

  try {
    var decompressed = Utilities.ungzip(gzipBlob).getBytes();
  } catch (e) {
    Logger.log("Decompression failed: " + e.message);
    return null;
  }

  // PNG 필터 해제 + 픽셀 추출
  var bytesPerPixel = colorType === 6 ? 4 : (colorType === 2 ? 3 : 1);
  var scanlineLen = width * bytesPerPixel + 1; // +1 = 필터 바이트
  var pixels = { width: width, height: height, data: [] };

  var prevLine = new Array(width * bytesPerPixel).fill(0);

  for (var y = 0; y < height; y++) {
    var lineStart = y * scanlineLen;
    if (lineStart >= decompressed.length) break;

    var filterType = decompressed[lineStart] & 0xFF;
    var line = [];

    for (var x = 0; x < width * bytesPerPixel; x++) {
      var raw = decompressed[lineStart + 1 + x] & 0xFF;
      var a = x >= bytesPerPixel ? line[x - bytesPerPixel] : 0;
      var b = prevLine[x];
      var c = (x >= bytesPerPixel) ? prevLine[x - bytesPerPixel] : 0;

      var val;
      if (filterType === 0) val = raw;
      else if (filterType === 1) val = (raw + a) & 0xFF;
      else if (filterType === 2) val = (raw + b) & 0xFF;
      else if (filterType === 3) val = (raw + Math.floor((a + b) / 2)) & 0xFF;
      else if (filterType === 4) val = (raw + paethPredictor(a, b, c)) & 0xFF;
      else val = raw;

      line.push(val);
    }

    // RGB 추출
    for (var x = 0; x < width; x++) {
      var idx = x * bytesPerPixel;
      pixels.data.push([line[idx], line[idx+1], line[idx+2]]);
    }

    prevLine = line;
  }

  return pixels;
}

function paethPredictor(a, b, c) {
  var p = a + b - c;
  var pa = Math.abs(p - a);
  var pb = Math.abs(p - b);
  var pc = Math.abs(p - c);
  if (pa <= pb && pa <= pc) return a;
  if (pb <= pc) return b;
  return c;
}

function resamplePixels(pixels, targetW, targetH) {
  // pixels.data: [{r,g,b}, ...] flat, pixels.width x pixels.height
  // → targetW x targetH로 리샘플 (nearest neighbor)
  var result = [];
  for (var y = 0; y < targetH; y++) {
    for (var x = 0; x < targetW; x++) {
      var srcX = Math.floor(x * pixels.width / targetW);
      var srcY = Math.floor(y * pixels.height / targetH);
      var idx = srcY * pixels.width + srcX;
      if (idx < pixels.data.length) {
        result.push(pixels.data[idx]);
      } else {
        result.push([128, 128, 128]);
      }
    }
  }
  return { width: targetW, height: targetH, data: result };
}

// ═══════════════════════════════════════
//  픽셀 → 28색 FieldMap
// ═══════════════════════════════════════

function nearestColorId(rgb, allowedIds) {
  var ids = allowedIds || PAL_KEYS;
  var bestId = ids[0];
  var bestDist = 999999;
  for (var i = 0; i < ids.length; i++) {
    var p = GAME_PALETTE[ids[i]];
    if (!p) continue;
    var d = (rgb[0]-p[0])*(rgb[0]-p[0]) + (rgb[1]-p[1])*(rgb[1]-p[1]) + (rgb[2]-p[2])*(rgb[2]-p[2]);
    if (d < bestDist) { bestDist = d; bestId = ids[i]; }
  }
  return bestId;
}

function pixelsToFieldMap(pixels, cols, rows, allowedIds) {
  var lines = [];
  for (var y = 0; y < rows; y++) {
    var line = [];
    for (var x = 0; x < cols; x++) {
      var idx = y * cols + x;
      var rgb = (pixels && idx < pixels.data.length) ? pixels.data[idx] : [128,128,128];
      var colorId = nearestColorId(rgb, allowedIds);
      line.push(String(colorId).padStart(2, "0"));
    }
    lines.push(line.join(" "));
  }
  return lines.join("\n");
}

// ═══════════════════════════════════════
//  FieldMap → 게임 팔레트 이미지 (BMP)
// ═══════════════════════════════════════

function fieldMapToImage(fieldMapText, cols, rows, scale) {
  // FieldMap "01 02 03\n04 05 01" → 게임 28색 BMP 이미지
  // scale: 각 셀을 몇 px로 (기본 4 → 31*4=124px)
  scale = scale || 4;
  var w = cols * scale;
  var h = rows * scale;

  var lines = fieldMapText.split("\n");

  // BMP 생성 (24비트, 비압축)
  var rowBytes = w * 3;
  var padding = (4 - (rowBytes % 4)) % 4;
  var dataSize = (rowBytes + padding) * h;
  var fileSize = 54 + dataSize;

  var bmp = [];

  // BMP Header (14 bytes)
  bmp.push(0x42, 0x4D); // "BM"
  pushLE32(bmp, fileSize);
  pushLE32(bmp, 0); // reserved
  pushLE32(bmp, 54); // pixel data offset

  // DIB Header (40 bytes)
  pushLE32(bmp, 40); // header size
  pushLE32(bmp, w);
  pushLE32(bmp, h);
  pushLE16(bmp, 1); // planes
  pushLE16(bmp, 24); // bits per pixel
  pushLE32(bmp, 0); // compression
  pushLE32(bmp, dataSize);
  pushLE32(bmp, 2835); // h resolution
  pushLE32(bmp, 2835); // v resolution
  pushLE32(bmp, 0); // colors
  pushLE32(bmp, 0); // important colors

  // Pixel data (bottom-up)
  for (var y = rows - 1; y >= 0; y--) {
    var tokens = y < lines.length ? lines[y].split(" ") : [];
    for (var sy = 0; sy < scale; sy++) {
      for (var x = 0; x < cols; x++) {
        var colorId = (x < tokens.length) ? parseInt(tokens[x]) : 1;
        var rgb = GAME_PALETTE[colorId] || [128, 128, 128];
        for (var sx = 0; sx < scale; sx++) {
          bmp.push(rgb[2], rgb[1], rgb[0]); // BGR
        }
      }
      for (var p = 0; p < padding; p++) bmp.push(0);
    }
  }

  return Utilities.newBlob(bmp, "image/bmp", "palette.bmp");
}

function pushLE16(arr, val) {
  arr.push(val & 0xFF, (val >> 8) & 0xFF);
}

function pushLE32(arr, val) {
  arr.push(val & 0xFF, (val >> 8) & 0xFF, (val >> 16) & 0xFF, (val >> 24) & 0xFF);
}

// ═══════════════════════════════════════
//  유틸
// ═══════════════════════════════════════

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

function colorIdsToNames(ids) {
  var names = {1:"pink",2:"cyan",3:"purple",4:"yellow",5:"lime green",6:"orange",
    7:"white",8:"dark gray",9:"sky blue",10:"green",11:"red",12:"blue",
    13:"teal",14:"lavender",15:"light blue",16:"brown",17:"peach",
    18:"light pink",19:"wine",20:"light green",21:"dark purple",
    22:"coral",23:"light gray",24:"gray",25:"magenta",26:"light orange",
    27:"dark red",28:"mint"};
  return ids.map(function(id) { return names[id] || ""; }).filter(Boolean).join(", ");
}

function noteToPrompt(note, numColors) {
  if (!note) return "colorful pixel art game level board, bright vivid colors, clean blocks";
  note = String(note);
  var motifMatch = note.match(/\[Motif\]\s*(?:구상|추상)?:?\s*([^\[]+)/);
  var motif = motifMatch ? motifMatch[1].trim() : "";
  var shapeMatch = note.match(/\[Shape\]\s*([^\[]+)/);
  var shape = shapeMatch ? shapeMatch[1].trim() : "";
  var compMatch = note.match(/\[Composition\]\s*([^\[]+)/);
  var comp = compMatch ? compMatch[1].trim() : "";

  var map = {"고양이 얼굴":"cute cat face","고양이":"cat","물고기":"fish swimming",
    "해 ":"bright sun ","나비":"butterfly with spread wings","음표":"music note",
    "격자":"grid pattern","줄무늬":"colorful stripes","기하학 패턴":"geometric pattern",
    "기하학":"geometric","체커":"checkerboard","소용돌이":"spiral swirl","타일":"repeating tile",
    "꽃":"flower","좌우대칭":"left-right symmetrical","4방향대칭":"4-way symmetrical",
    "원형":"circular round shape","하트":"heart shape","계단":"staircase diagonal steps",
    "삼각형":"triangle","화살표":"arrow pointing","꽉찬 사각형":"filled rectangle",
    "L자":"L-shaped block","벌":"cute bee","곰":"cute bear","별":"shining star",
    "눈사람":"snowman","펭귄":"penguin","강아지":"puppy dog","토끼":"rabbit",
    "당근":"orange carrot","버섯":"red mushroom","호박":"orange pumpkin",
    "그라데이션":"gradient","외곽 테두리 강조":"bold border frame","외곽":"outer border",
    "중심":"center","동심원":"concentric circles","분산":"scattered distributed",
    "유닛 타일링":"unit tiling","단색블록":"solid color blocks","상하대칭":"top-bottom symmetrical",
    "대각선":"diagonal"};

  function tr(t) { var r = t; var k = Object.keys(map); for(var i=0;i<k.length;i++) r=r.replace(new RegExp(k[i],"g"),map[k[i]]); return r.replace(/휴식\.?|하드\.?|도입\.?/g,"").replace(/\s+/g," ").trim(); }

  var parts = [];
  if (motif) parts.push(tr(motif));
  if (shape) parts.push(tr(shape));
  if (comp) parts.push(tr(comp));
  if (numColors) {
    var n = parseInt(numColors);
    if (n <= 3) parts.push("simple " + n + " colors");
    else if (n <= 5) parts.push("vibrant " + n + " colors");
    else parts.push("rich " + n + " colors rainbow palette");
  }
  if (parts.length === 0) parts.push("abstract colorful pattern");
  return parts.join(", ") + ", pixel art game level board, clean bright vivid blocks, top-down view";
}

// ═══════════════════════════════════════
//  API
// ═══════════════════════════════════════

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

// ═══════════════════════════════════════
//  Drive 저장
// ═══════════════════════════════════════

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
  return { url: file.getUrl(), downloadUrl: "https://drive.google.com/uc?export=download&id=" + file.getId(), jsonContent: jsonStr };
}

// ═══════════════════════════════════════
//  사이드바 호출
// ═══════════════════════════════════════

function getSelectedRowsData() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var sel = sheet.getActiveRange();
  var headers = getHeaders();
  var lastCol = sheet.getLastColumn();
  var levelIdx = col(headers, "level_number");
  var rowsIdx = col(headers, "field_rows");
  var colsIdx = col(headers, "field_columns");
  var noteIdx = col(headers, "designer_note");
  var ncIdx = col(headers, "num_colors");

  var results = [];
  for (var r = sel.getRow(); r < sel.getRow() + sel.getNumRows(); r++) {
    if (r < DATA_START) continue;
    var d = sheet.getRange(r, 1, 1, lastCol).getValues()[0];
    var note = noteIdx >= 0 ? String(d[noteIdx]) : "";
    var nc = ncIdx >= 0 ? d[ncIdx] : 4;
    results.push({
      row: r,
      level: levelIdx >= 0 ? d[levelIdx] : r,
      cols: colsIdx >= 0 ? parseInt(d[colsIdx]) || 20 : 20,
      rows: rowsIdx >= 0 ? parseInt(d[rowsIdx]) || 20 : 20,
      prompt: noteToPrompt(note, nc),
    });
  }
  return results;
}

function getSelectedRowData() {
  var data = getSelectedRowsData();
  return data.length > 0 ? data[0] : null;
}

function generateFromSidebar(rowIndex, customPrompt, folderName) {
  var headers = getHeaders();
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var lastCol = sheet.getLastColumn();
  var rowData = sheet.getRange(rowIndex, 1, 1, lastCol).getValues()[0];

  function g(name) { var i = col(headers, name); return i >= 0 ? rowData[i] : null; }
  function gi(name, def) { var v = g(name); return v !== null ? (parseInt(v) || def) : def; }
  function gf(name, def) { var v = g(name); return v !== null ? (parseFloat(v) || def) : def; }
  function gs(name, def) { var v = g(name); return v !== null ? String(v) : (def || ""); }

  var levelNum = gi("level_number", rowIndex);
  var fieldCols = gi("field_columns", 20);
  var fieldRows = gi("field_rows", 20);
  var numColors = gi("num_colors", 4);
  var prompt = customPrompt || "pixel art pattern";
  var filename = "level_" + String(levelNum).padStart(3, "0") + "_" + fieldCols + "x" + fieldRows + ".png";
  var jsonFilename = filename.replace(".png", ".json");

  // 색상 제한
  var colorDist = gs("color_distribution", "");
  var colorIds = parseColorDist(colorDist);
  if (colorIds.length === 0) { for (var i = 1; i <= numColors; i++) colorIds.push(i); }
  var colorNames = colorIdsToNames(colorIds);
  if (colorNames) prompt += ", using only " + colorNames + " colors";

  // 1. PixelLab API — 정확한 그리드 크기로 생성 (1픽셀=1셀)
  //    최소 32px 제한 → 작은 쪽을 32로 맞추고 비율 유지
  var apiW = Math.max(32, fieldCols);
  var apiH = Math.max(32, fieldRows);
  var imgB64 = callPixelLab(prompt, apiW, apiH);

  // 2. 원본 이미지 → 픽셀 분석 → FieldMap
  var fieldMap = "";
  var pixels = pngToPixels(imgB64, fieldCols, fieldRows);
  if (pixels) {
    fieldMap = pixelsToFieldMap(pixels, fieldCols, fieldRows, colorIds);
  } else {
    // fallback
    var lines = [];
    for (var y = 0; y < fieldRows; y++) {
      var line = [];
      for (var x = 0; x < fieldCols; x++) {
        line.push(String(colorIds[(x+y) % colorIds.length]).padStart(2, "0"));
      }
      lines.push(line.join(" "));
    }
    fieldMap = lines.join("\n");
  }

  // 3. 게임 팔레트 색상 이미지 생성 (FieldMap 기반 — 유니티와 동일한 색상)
  var paletteBmpBlob = fieldMapToImage(fieldMap, fieldCols, fieldRows, 8);

  // 4. 팔레트 이미지를 메인 이미지로 저장 (유니티에서 보이는 색상 그대로)
  var paletteFilename = filename.replace(".png", "_palette.bmp");
  var paletteFolder = getOutputFolder(folderName);
  var existPal = paletteFolder.getFilesByName(paletteFilename);
  if (existPal.hasNext()) existPal.next().setTrashed(true);
  var palFile = paletteFolder.createFile(paletteBmpBlob.setName(paletteFilename));
  palFile.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  var paletteUrl = "https://drive.google.com/uc?export=download&id=" + palFile.getId();

  // PixelLab 원본도 참고용으로 저장
  var imgResult = saveToDrive(imgB64, filename, folderName);

  // 5. designer_note에 [FieldMap] 추가
  var paletteFilename = filename.replace(".png", "_palette.bmp");
  var paletteBmp = fieldMapToImage(fieldMap, fieldCols, fieldRows, 4);
  var paletteFolder = getOutputFolder(folderName);
  var existPal = paletteFolder.getFilesByName(paletteFilename);
  if (existPal.hasNext()) existPal.next().setTrashed(true);
  var palFile = paletteFolder.createFile(paletteBmp.setName(paletteFilename));
  palFile.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  var paletteUrl = "https://drive.google.com/uc?export=download&id=" + palFile.getId();

  // 5. designer_note에 [FieldMap] 추가
  var designerNote = gs("designer_note", "");
  var fmIdx = designerNote.indexOf("[FieldMap]");
  if (fmIdx >= 0) designerNote = designerNote.substring(0, fmIdx).trim();
  designerNote += "\n[FieldMap]\n" + fieldMap;

  // 5. Unity 호환 JSON 생성
  var levelJson = {
    level_number: levelNum,
    level_id: gs("level_id", "BF_" + String(levelNum).padStart(3, "0")),
    pkg: gi("pkg", 1), pos: gi("pos", 1), chapter: gi("chapter", 1),
    purpose_type: gs("purpose_type", "노말"),
    target_cr: gi("target_cr", 60), target_attempts: gf("target_attempts", 1.8),
    num_colors: numColors, color_distribution: gs("color_distribution", ""),
    field_rows: fieldRows, field_columns: fieldCols,
    total_cells: gi("total_cells", fieldRows * fieldCols),
    rail_capacity: gi("rail_capacity", 160), rail_capacity_tier: gs("rail_capacity_tier", "701+"),
    queue_columns: gi("queue_columns", 2), queue_rows: gi("queue_rows", 20),
    gimmick_hidden: gi("gimmick_hidden",0), gimmick_chain: gi("gimmick_chain",0),
    gimmick_pinata: gi("gimmick_pinata",0), gimmick_spawner_t: gi("gimmick_spawner_t",0),
    gimmick_pin: gi("gimmick_pin",0), gimmick_lock_key: gi("gimmick_lock_key",0),
    gimmick_surprise: gi("gimmick_surprise",0), gimmick_wall: gi("gimmick_wall",0),
    gimmick_spawner_o: gi("gimmick_spawner_o",0), gimmick_pinata_box: gi("gimmick_pinata_box",0),
    gimmick_ice: gi("gimmick_ice",0), gimmick_frozen_dart: gi("gimmick_frozen_dart",0),
    gimmick_curtain: gi("gimmick_curtain",0),
    total_darts: gi("total_darts", 0), dart_capacity_range: gs("dart_capacity_range", ""),
    emotion_curve: gs("emotion_curve", ""), designer_note: designerNote,
    pixel_art_source: filename,
  };

  var jsonResult = saveJson(levelJson, jsonFilename, folderName);

  return {
    imgUrl: imgResult.url, imgDownloadUrl: imgResult.downloadUrl,
    jsonUrl: jsonResult.url, jsonDownloadUrl: jsonResult.downloadUrl,
    paletteUrl: paletteUrl, paletteFilename: paletteFilename,
    jsonContent: jsonResult.jsonContent,
    filename: filename, jsonFilename: jsonFilename, prompt: prompt,
  };
}

function generateSelectedRows(folderName) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var sel = sheet.getActiveRange();
  var headers = getHeaders();
  var ncIdx = col(headers, "num_colors");
  var noteIdx = col(headers, "designer_note");
  var results = [];
  for (var i = sel.getRow(); i < sel.getRow() + sel.getNumRows(); i++) {
    if (i < DATA_START) continue;
    try {
      var d = sheet.getRange(i, 1, 1, sheet.getLastColumn()).getValues()[0];
      var note = noteIdx >= 0 ? String(d[noteIdx]) : "";
      var nc = ncIdx >= 0 ? d[ncIdx] : 4;
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
  var ncIdx = col(headers, "num_colors");
  var count = 0;
  for (var i = DATA_START; i <= sheet.getLastRow(); i++) {
    if (srcIdx >= 0) {
      var val = sheet.getRange(i, srcIdx + 1).getValue();
      if (val && String(val).trim()) continue;
    }
    try {
      var d = sheet.getRange(i, 1, 1, sheet.getLastColumn()).getValues()[0];
      var note = noteIdx >= 0 ? String(d[noteIdx]) : "";
      var nc = ncIdx >= 0 ? d[ncIdx] : 4;
      generateFromSidebar(i, noteToPrompt(note, nc), folderName);
      count++;
    } catch (e) { Logger.log("Row " + i + ": " + e.message); }
    Utilities.sleep(1000);
  }
  SpreadsheetApp.getUi().alert(count + "개 완료");
}
