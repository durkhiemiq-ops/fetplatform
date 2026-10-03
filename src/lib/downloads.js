// RFC 5987 filename* is encoded; ordinary filename values are literal text.
export const downloadFilename = (disposition, fallback) => {
  const encoded = /(?:^|;)\s*filename\*=UTF-8'[^']*'([^;]+)/i.exec(disposition);
  if (encoded) {
    try {
      const value = decodeURIComponent(encoded[1].trim().replace(/^"|"$/g, ''));
      if (value) return value;
    } catch {
      // A malformed extended value must not prevent a successful download.
    }
  }
  const plain = /(?:^|;)\s*filename=(?:"((?:\\.|[^"\\])*)"|([^;]*))/i.exec(disposition);
  return plain ? (plain[1]?.replace(/\\(.)/g, '$1') || plain[2]?.trim() || fallback) : fallback;
};
