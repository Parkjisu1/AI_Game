/**
 * search-strategy.js - 하이브리드 검색 전략 (구조화 + 코사인 유사도)
 *
 * DB 규모에 따라 자동 전환:
 *   - 소규모 (< COSINE_THRESHOLD): 구조화 필터링 + 메타데이터 스코어링만 사용
 *   - 대규모 (>= COSINE_THRESHOLD): 구조화 필터링 후 코사인 유사도로 리랭킹
 *
 * 구조화 검색이 1차 필터 역할을 하고, 코사인 유사도는
 * 동일 genre+domain 내에서 "어떤 항목이 더 관련성 높은가"를 판별하는 2차 랭킹.
 */

// ============================================================
// Configuration
// ============================================================

/**
 * 동일 검색 조건(genre+domain)에서 후보가 이 수 이상이면 코사인 유사도 활성화
 * 근거: 30건 미만이면 구조화 필터링만으로 충분히 좁혀짐
 *       30건 이상이면 같은 조건 내에서 세부 랭킹이 필요해짐
 */
const COSINE_THRESHOLD = 30;

/**
 * 코사인 유사도의 최종 스코어 반영 비중
 * totalScore = structuredScore * (1 - COSINE_WEIGHT) + cosineScore * COSINE_WEIGHT
 */
const COSINE_WEIGHT = 0.3;

// ============================================================
// TF-IDF 기반 코사인 유사도 (외부 의존성 없음)
// ============================================================

/**
 * 텍스트를 토큰으로 분리 (한/영/숫자 지원)
 */
function tokenize(text) {
    if (!text) return [];
    const str = String(text).toLowerCase();
    // 한글 음절, 영문, 숫자 단위로 분리
    const tokens = str.match(/[가-힣]+|[a-z_][a-z0-9_]*|[0-9]+/g);
    return tokens || [];
}

/**
 * 엔트리에서 검색 가능한 텍스트 필드들을 합쳐 토큰 배열로 반환
 */
function extractTokens(entry) {
    const parts = [];
    if (entry.system) parts.push(entry.system);
    if (entry.designId) parts.push(entry.designId);
    if (entry.fileId) parts.push(entry.fileId);
    if (entry.domain) parts.push(entry.domain);
    if (entry.data_type) parts.push(entry.data_type);
    if (entry.balance_area) parts.push(entry.balance_area);
    if (entry.role) parts.push(entry.role);
    if (Array.isArray(entry.tags)) parts.push(entry.tags.join(' '));
    if (Array.isArray(entry.provides)) parts.push(entry.provides.join(' '));
    if (Array.isArray(entry.requires)) parts.push(entry.requires.join(' '));
    return tokenize(parts.join(' '));
}

/**
 * 쿼리 args에서 검색 의도 토큰 추출
 */
function extractQueryTokens(args) {
    const parts = [];
    if (args.system) parts.push(args.system);
    if (args.domain) parts.push(args.domain);
    if (args.data_type) parts.push(args.data_type);
    if (args.balance_area) parts.push(args.balance_area);
    if (args.role) parts.push(args.role);
    if (args.provides) parts.push(args.provides);
    return tokenize(parts.join(' '));
}

/**
 * TF (Term Frequency) 계산
 */
function computeTF(tokens) {
    const tf = {};
    for (const t of tokens) {
        tf[t] = (tf[t] || 0) + 1;
    }
    const len = tokens.length || 1;
    for (const t in tf) {
        tf[t] /= len;
    }
    return tf;
}

/**
 * IDF (Inverse Document Frequency) 계산
 */
function computeIDF(documents) {
    const df = {};
    const N = documents.length || 1;
    for (const doc of documents) {
        const seen = new Set(doc);
        for (const t of seen) {
            df[t] = (df[t] || 0) + 1;
        }
    }
    const idf = {};
    for (const t in df) {
        idf[t] = Math.log(N / df[t]) + 1; // smoothed IDF
    }
    return idf;
}

/**
 * TF-IDF 벡터 생성
 */
function computeTFIDF(tf, idf) {
    const vec = {};
    for (const t in tf) {
        vec[t] = tf[t] * (idf[t] || 1);
    }
    return vec;
}

/**
 * 두 벡터의 코사인 유사도 계산
 */
function cosineSimilarity(vecA, vecB) {
    let dot = 0, magA = 0, magB = 0;

    for (const t in vecA) {
        if (vecB[t]) dot += vecA[t] * vecB[t];
        magA += vecA[t] * vecA[t];
    }
    for (const t in vecB) {
        magB += vecB[t] * vecB[t];
    }

    magA = Math.sqrt(magA);
    magB = Math.sqrt(magB);

    if (magA === 0 || magB === 0) return 0;
    return dot / (magA * magB);
}

// ============================================================
// Hybrid Search Strategy
// ============================================================

/**
 * 하이브리드 스코어 계산
 *
 * @param {Array} filteredResults - 구조화 필터링을 통과한 결과 배열
 * @param {Object} args - 검색 쿼리 인자
 * @param {Function} structuredScoreFn - 기존 구조화 스코어링 함수 (entry, args) => number
 * @returns {Array} - cosineScore, structuredScore, hybridScore가 추가된 결과 배열
 */
function applyHybridScoring(filteredResults, args, structuredScoreFn) {
    const count = filteredResults.length;
    const useCosine = count >= COSINE_THRESHOLD;

    if (!useCosine) {
        // 소규모: 구조화 스코어만 사용
        return filteredResults.map(entry => ({
            ...entry,
            matchScore: structuredScoreFn(entry, args),
            _searchMode: 'structured',
            _candidateCount: count,
        }));
    }

    // 대규모: 구조화 + 코사인 하이브리드
    const queryTokens = extractQueryTokens(args);
    if (queryTokens.length === 0) {
        // 쿼리 토큰이 없으면 구조화만 사용
        return filteredResults.map(entry => ({
            ...entry,
            matchScore: structuredScoreFn(entry, args),
            _searchMode: 'structured (no query tokens)',
            _candidateCount: count,
        }));
    }

    // 모든 문서의 토큰 추출
    const allDocTokens = filteredResults.map(entry => extractTokens(entry));

    // IDF 계산 (전체 문서 기반)
    const idf = computeIDF(allDocTokens);

    // 쿼리 TF-IDF 벡터
    const queryTF = computeTF(queryTokens);
    const queryVec = computeTFIDF(queryTF, idf);

    // 각 문서의 코사인 유사도 계산
    const results = filteredResults.map((entry, idx) => {
        const docTF = computeTF(allDocTokens[idx]);
        const docVec = computeTFIDF(docTF, idf);
        const cosScore = cosineSimilarity(queryVec, docVec);
        const structScore = structuredScoreFn(entry, args);

        // 하이브리드 스코어: 구조화 (70%) + 코사인 (30%)
        const hybridScore = structScore * (1 - COSINE_WEIGHT) + cosScore * COSINE_WEIGHT;

        return {
            ...entry,
            matchScore: hybridScore,
            _cosineScore: parseFloat(cosScore.toFixed(4)),
            _structuredScore: parseFloat(structScore.toFixed(4)),
            _searchMode: 'hybrid',
            _candidateCount: count,
        };
    });

    return results;
}

/**
 * 현재 검색 모드 정보 반환 (디버깅/로그용)
 */
function getSearchModeInfo(candidateCount) {
    return {
        mode: candidateCount >= COSINE_THRESHOLD ? 'hybrid' : 'structured',
        threshold: COSINE_THRESHOLD,
        candidateCount,
        cosineWeight: candidateCount >= COSINE_THRESHOLD ? COSINE_WEIGHT : 0,
        reason: candidateCount >= COSINE_THRESHOLD
            ? `후보 ${candidateCount}건 >= 임계값 ${COSINE_THRESHOLD} → 코사인 유사도 활성화 (비중 ${COSINE_WEIGHT * 100}%)`
            : `후보 ${candidateCount}건 < 임계값 ${COSINE_THRESHOLD} → 구조화 검색만 사용`,
    };
}

// ============================================================
// Exports
// ============================================================

module.exports = {
    COSINE_THRESHOLD,
    COSINE_WEIGHT,
    applyHybridScoring,
    getSearchModeInfo,
    // 개별 함수도 export (테스트/커스텀용)
    tokenize,
    extractTokens,
    extractQueryTokens,
    cosineSimilarity,
    computeTF,
    computeIDF,
    computeTFIDF,
};
