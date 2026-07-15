export interface IceFishingBackdropRef {
  current: CanvasImageSource | null;
}

type BackdropImage = HTMLImageElement;

const BACKDROP_WIDTH = 960;
const BACKDROP_HEIGHT = 600;

/** Load the authored plate without taking authority from the procedural game. */
export function loadIceFishingBackdrop(
  source: string,
  target: IceFishingBackdropRef,
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
