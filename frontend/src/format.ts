export const money = (n: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(n || 0);
export const human = (s: string) =>
  s
    ?.toLowerCase()
    .replaceAll("_", " ")
    .replace(/^./, (x) => x.toUpperCase()) || "Not assessed";
