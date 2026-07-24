/** Medium names show in full; longer ones get a middle-ellipsis keeping the
 * start and the file extension. Pair with title={fullName} for hover. */
export function truncateFilename(name: string, max = 48): string {
  if (name.length <= max) return name;
  const head = name.slice(0, max - 12);
  const tail = name.slice(-9); // keeps "…xxxxx.pdf" so the extension stays visible
  return `${head}…${tail}`;
}
