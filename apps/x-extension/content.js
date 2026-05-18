// Content script — runs inside x.com / twitter.com pages.
//
// Responsibilities:
// 1. Listen for messages from the popup ("capture-thread")
// 2. Walk the DOM, extract the current status page's thread
// 3. Return the structured payload to the popup which then POSTs
//    it to the substrate.
//
// Why DOM-walking and not the API: the X API requires a paid tier
// the operator does not maintain, and even then thread reconstruction
// is non-trivial. The DOM is the canonical text the user sees, which
// is exactly what we want to capture.

(() => {
  const TWEET_ARTICLE_SEL = 'article[data-testid="tweet"]';

  function getTweetIdFromAnchor(article) {
    // Tweet permalink anchor is the simplest way to recover the id.
    const a = article.querySelector('a[href*="/status/"][role="link"]');
    if (!a) return null;
    const m = a.href.match(/\/status\/(\d+)/);
    return m ? m[1] : null;
  }

  function getHandleFromArticle(article) {
    // Author handle lives in a span like "@foo"
    const span = article.querySelector('div[data-testid="User-Name"] a[href^="/"]');
    if (!span) return null;
    const m = span.getAttribute("href")?.match(/^\/([A-Za-z0-9_]+)/);
    return m ? m[1] : null;
  }

  function getTweetText(article) {
    const node = article.querySelector('div[data-testid="tweetText"]');
    return node ? node.innerText.trim() : "";
  }

  function getPostedAt(article) {
    const time = article.querySelector("time");
    return time ? time.getAttribute("datetime") : null;
  }

  function isVerified(article) {
    return !!article.querySelector('svg[aria-label="Verified account"]');
  }

  function getMediaUrls(article) {
    const urls = [];
    article.querySelectorAll('img[alt="Image"]').forEach((img) => {
      if (img.src) urls.push(img.src);
    });
    return urls;
  }

  function captureThread() {
    const path = window.location.pathname;
    const m = path.match(/^\/([^/]+)\/status\/(\d+)/);
    if (!m) {
      return {
        ok: false,
        error:
          "Not a status page. Open a tweet (URL contains /status/) and try again.",
      };
    }
    const rootAuthor = m[1];
    const rootId = m[2];

    const articles = Array.from(document.querySelectorAll(TWEET_ARTICLE_SEL));
    if (articles.length === 0) {
      return {
        ok: false,
        error: "No tweets found on this page. The DOM may have changed.",
      };
    }

    const tweets = [];
    for (const article of articles) {
      const tweetId = getTweetIdFromAnchor(article);
      const handle = getHandleFromArticle(article);
      const text = getTweetText(article);
      if (!tweetId || !text) continue;
      tweets.push({
        tweet_id: tweetId,
        author_handle: handle || rootAuthor,
        text,
        author_verified: isVerified(article),
        posted_at: getPostedAt(article),
        reply_to: null,
        quote_of: null,
        media_urls: getMediaUrls(article),
      });
    }

    if (tweets.length === 0) {
      return {
        ok: false,
        error:
          "Could not extract any tweet text. The DOM selectors may need updating.",
      };
    }

    // Best-effort reply chain: tweets after the first are reply_to the prior one
    // when they share the author. The substrate doesn't depend on this being
    // perfect; it's used for thread reconstruction in display.
    for (let i = 1; i < tweets.length; i++) {
      if (tweets[i].author_handle === tweets[i - 1].author_handle) {
        tweets[i].reply_to = tweets[i - 1].tweet_id;
      }
    }

    return {
      ok: true,
      payload: {
        thread_url: window.location.origin + window.location.pathname,
        root_tweet_id: rootId,
        author_handle: rootAuthor,
        tweets,
      },
    };
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg && msg.type === "antiek-capture-thread") {
      sendResponse(captureThread());
      return true;
    }
    return false;
  });
})();
