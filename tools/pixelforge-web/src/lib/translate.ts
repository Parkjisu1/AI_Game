export async function koToEn(text: string): Promise<string> {
  // 한글이 없으면 그대로 반환
  if (!/[\uAC00-\uD7AF]/.test(text)) return text;

  try {
    const url = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=ko&tl=en&dt=t&q=${encodeURIComponent(text)}`;
    const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
    const data = await res.json();
    const translated = data[0].map((s: string[]) => s[0]).join("");
    return translated;
  } catch {
    // 번역 실패 시 원본 반환
    return text;
  }
}
