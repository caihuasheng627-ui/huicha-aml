export const TOKEN_SPLIT =
  /(EV-[A-Z0-9\-]+|TX-[A-Z0-9\-]+|6222-[A-Z0-9\-]+|CASH-\d+|C-[A-Z0-9]+|KB-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)/;
export const TOKEN_ONE =
  /^(EV-[A-Z0-9\-]+|TX-[A-Z0-9\-]+|6222-[A-Z0-9\-]+|CASH-\d+|C-[A-Z0-9]+|KB-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)$/;

export function splitEvidenceParts(text) {
  return String(text || "").split(TOKEN_SPLIT);
}

export function isEvidenceToken(part) {
  return TOKEN_ONE.test(part);
}
