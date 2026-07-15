export interface FjordSkipBackdropRef {
  current: CanvasImageSource | null;
}

type BackdropImage = HTMLImageElement;

const BACKDROP_WIDTH = 960;
const BACKDROP_HEIGHT = 600;

/**
 * Loads the authored fjord field plate without owning game state.
 *
 * Exact-dimension gate: rejects any decode whose naturalWidth × naturalHeight
 * does not match 960 × 600. Until load succeeds, the renderer keeps its
 * complete procedural fallback. Late callbacks become inert on teardown.
 */
export function loadFjordSkipBackdrop(
  source: string,
  target: FjordSkipBackdropRef,
  createImage: () => BackdropImage = () => new Image(),
  onReady?: () => void,
): () => void {
  const image = createImage();
  let live = true;
  image.onload = () => {
    if (
      live &&
      image.naturalWidth === BACKDROP_WIDTH &&
      image.naturalHeight === BACKDROP_HEIGHT
    ) {
      target.current = image;
      onReady?.();
    }
  };
  image.onerror = () => {
    if (live && target.current === image) target.current = null;
  };
  image.src = source;

  return () => {
    live = false;
    if (target.current === image) target.current = null;
    image.onload = null;
    image.onerror = null;
  };
}
