/** Display-only decimal formatting. Never convert a money/quantity string to binary float. */
export function formatDecimal(
  value: string | null | undefined,
  kind: "money" | "quantity" | "percent" = "money",
  locale = "en-US",
): string {
  if (
    value == null ||
    value.length > 256 ||
    !/^-?(0|[1-9]\d*)(\.\d+)?$/.test(value)
  )
    return "Unavailable";
  const negative = value.startsWith("-");
  const [integer, fraction = ""] = value.replace(/^-/, "").split(".");
  const digits = kind === "quantity" ? 6 : 2;
  const shift = kind === "percent" ? 2 : 0;
  const raw = BigInt(integer + fraction);
  const exponent = digits + shift - fraction.length;
  const divisor = exponent < 0 ? 10n ** BigInt(-exponent) : 1n;
  const scaled =
    exponent >= 0
      ? raw * 10n ** BigInt(exponent)
      : (raw + divisor / 2n) / divisor;
  const base = 10n ** BigInt(digits);
  const whole = scaled / base;
  let tail = (scaled % base).toString().padStart(digits, "0");
  if (kind !== "money") tail = tail.replace(/0+$/, "");
  const style =
    kind === "money" ? "currency" : kind === "percent" ? "percent" : "decimal";
  try {
    const grouped = new Intl.NumberFormat(locale, {
      maximumFractionDigits: 0,
    }).format(whole);
    const localizedTail = tail
      ? new Intl.NumberFormat(locale, {
          useGrouping: false,
          minimumIntegerDigits: tail.length,
        }).format(Number(tail))
      : "";
    let emitted = false;
    return new Intl.NumberFormat(locale, {
      style,
      currency: "USD",
      minimumFractionDigits: tail.length,
      maximumFractionDigits: tail.length,
    })
      .formatToParts(negative && raw !== 0n ? -1 : 1)
      .map((part) => {
        if (part.type === "integer") {
          if (emitted) return "";
          emitted = true;
          return grouped;
        }
        if (part.type === "group") return "";
        if (part.type === "fraction") return localizedTail;
        return part.value;
      })
      .join("");
  } catch {
    return "Unavailable";
  }
}
