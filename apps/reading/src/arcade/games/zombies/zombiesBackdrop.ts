export interface ZombiesBackdropRef {
  current: CanvasImageSource | null;
}

type BackdropImage = HTMLImageElement;

const BACKDROP_WIDTH = 480;
const BACKDROP_HEIGHT = 300;

/**
 * Loads a bundled visual plate without owning game state. Until load succeeds,
 * the renderer keeps its complete procedural fallback. Late callbacks become
 * inert on teardown.
 */
export function loadZombiesBackdrop(
  source: string,
  target: ZombiesBackdropRef,
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
