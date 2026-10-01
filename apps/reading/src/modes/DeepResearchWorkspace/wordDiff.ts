/**
 * wordDiff.ts — the side-by-side picker's word-level diff (thread-merge +
 * document fork SPR-03, the SPR-00 verdict's picker: a word-level LCS with
 * the wrong-accept-suppressing layout). Pure: two strings in, aligned
 * segments out. A word present on both sides is `same`; otherwise it is
 * `left`/`right` (that side only). Small inputs only (a claim vs a pinned
 * passage) — the LCS table is O(n·m) words, fine at passage scale.
 */

export interface WordSegment {
  text: string;
  side: "same" | "left" | "right";
}

export interface WordDiff {
  left: WordSegment[];
  right: WordSegment[];
}

function words(value: string): string[] {
  return value.trim().split(/\s+/).filter(Boolean);
}

export function wordDiff(leftText: string, rightText: string): WordDiff {
  const a = words(leftText);
  const b = words(rightText);
  // LCS table.
  const table: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  );
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i][j] =
        a[i] === b[j]
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  const left: WordSegment[] = [];
  const right: WordSegment[] = [];
  const push = (list: WordSegment[], text: string, side: WordSegment["side"]) => {
    const last = list[list.length - 1];
    if (last && last.side === side) last.text += " " + text;
    else list.push({ text, side });
  };
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      push(left, a[i], "same");
      push(right, b[j], "same");
      i++;
      j++;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      push(left, a[i], "left");
      i++;
    } else {
      push(right, b[j], "right");
      j++;
    }
  }
  while (i < a.length) push(left, a[i++], "left");
  while (j < b.length) push(right, b[j++], "right");
  return { left, right };
}
