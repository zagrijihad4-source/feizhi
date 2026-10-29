var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/index.ts
var index_exports = {};
__export(index_exports, {
  copyToClipboard: () => copyToClipboard,
  emojiCodes: () => emojiCodes,
  emojiMap: () => emojiMap,
  extractTextFromHtml: () => extractTextFromHtml,
  isClipboardSupported: () => isClipboardSupported,
  renderWechatEmoji: () => renderWechatEmoji,
  wechatEmojis: () => wechatEmojis
});
module.exports = __toCommonJS(index_exports);

// src/core/data.ts
var size = 32;
var totalRows = 12;
var totalCols = 9;
var wechatEmojis = [
  { name: "\u5FAE\u7B11", code: "[\u5FAE\u7B11]", position: [1, 1] },
  { name: "\u6487\u5634", code: "[\u6487\u5634]", position: [1, 2] },
  { name: "\u8272", code: "[\u8272]", position: [1, 3] },
  { name: "\u53D1\u5446", code: "[\u53D1\u5446]", position: [1, 4] },
  { name: "\u5F97\u610F", code: "[\u5F97\u610F]", position: [1, 5] },
  { name: "\u6D41\u6CEA", code: "[\u6D41\u6CEA]", position: [1, 6] },
  { name: "\u5BB3\u7F9E", code: "[\u5BB3\u7F9E]", position: [1, 7] },
  { name: "\u95ED\u5634", code: "[\u95ED\u5634]", position: [1, 8] },
  { name: "\u7761", code: "[\u7761]", position: [1, 9] },
  { name: "\u5927\u54ED", code: "[\u5927\u54ED]", position: [2, 1] },
  { name: "\u5C34\u5C2C", code: "[\u5C34\u5C2C]", position: [2, 2] },
  { name: "\u53D1\u6012", code: "[\u53D1\u6012]", position: [2, 3] },
  { name: "\u8C03\u76AE", code: "[\u8C03\u76AE]", position: [2, 4] },
  { name: "\u5472\u7259", code: "[\u5472\u7259]", position: [2, 5] },
  { name: "\u60CA\u8BB6", code: "[\u60CA\u8BB6]", position: [2, 6] },
  { name: "\u96BE\u8FC7", code: "[\u96BE\u8FC7]", position: [2, 7] },
  { name: "\u51B7\u6C57", code: "[\u51B7\u6C57]", position: [2, 8] },
  { name: "\u6293\u72C2", code: "[\u6293\u72C2]", position: [2, 9] },
  { name: "\u5410", code: "[\u5410]", position: [3, 1] },
  { name: "\u5077\u7B11", code: "[\u5077\u7B11]", position: [3, 2] },
  { name: "\u6109\u5FEB", code: "[\u6109\u5FEB]", position: [3, 3] },
  { name: "\u767D\u773C", code: "[\u767D\u773C]", position: [3, 4] },
  { name: "\u50B2\u6162", code: "[\u50B2\u6162]", position: [3, 5] },
  { name: "\u56F0", code: "[\u56F0]", position: [3, 6] },
  { name: "\u60CA\u6050", code: "[\u60CA\u6050]", position: [3, 7] },
  { name: "\u61A8\u7B11", code: "[\u61A8\u7B11]", position: [3, 8] },
  { name: "\u60A0\u95F2", code: "[\u60A0\u95F2]", position: [3, 9] },
  { name: "\u5492\u9A82", code: "[\u5492\u9A82]", position: [4, 1] },
  { name: "\u7591\u95EE", code: "[\u7591\u95EE]", position: [4, 2] },
  { name: "\u5618", code: "[\u5618]", position: [4, 3] },
  { name: "\u6655", code: "[\u6655]", position: [4, 4] },
  { name: "\u8870", code: "[\u8870]", position: [4, 5] },
  { name: "\u9AB7\u9AC5", code: "[\u9AB7\u9AC5]", position: [4, 6] },
  { name: "\u6572\u6253", code: "[\u6572\u6253]", position: [4, 7] },
  { name: "\u518D\u89C1", code: "[\u518D\u89C1]", position: [4, 8] },
  { name: "\u64E6\u6C57", code: "[\u64E6\u6C57]", position: [4, 9] },
  { name: "\u62A0\u9F3B", code: "[\u62A0\u9F3B]", position: [5, 1] },
  { name: "\u9F13\u638C", code: "[\u9F13\u638C]", position: [5, 2] },
  { name: "\u574F\u7B11", code: "[\u574F\u7B11]", position: [5, 3] },
  { name: "\u53F3\u54FC\u54FC", code: "[\u53F3\u54FC\u54FC]", position: [5, 4] },
  { name: "\u9119\u89C6", code: "[\u9119\u89C6]", position: [5, 5] },
  { name: "\u5FEB\u54ED\u4E86", code: "[\u5FEB\u54ED\u4E86]", position: [5, 6] },
  { name: "\u59D4\u5C48", code: "[\u59D4\u5C48]", position: [5, 7] },
  { name: "\u9634\u9669", code: "[\u9634\u9669]", position: [5, 8] },
  { name: "\u4EB2\u4EB2", code: "[\u4EB2\u4EB2]", position: [5, 9] },
  { name: "\u53EF\u601C", code: "[\u53EF\u601C]", position: [6, 1] },
  { name: "\u7B11\u8138", code: "[\u7B11\u8138]", position: [6, 2] },
  { name: "\u751F\u75C5", code: "[\u751F\u75C5]", position: [6, 3] },
  { name: "\u8138\u7EA2", code: "[\u8138\u7EA2]", position: [6, 4] },
  { name: "\u7834\u6D95\u4E3A\u7B11", code: "[\u7834\u6D95\u4E3A\u7B11]", position: [6, 5] },
  { name: "\u6050\u60E7", code: "[\u6050\u60E7]", position: [6, 6] },
  { name: "\u5931\u671B", code: "[\u5931\u671B]", position: [6, 7] },
  { name: "\u65E0\u8BED", code: "[\u65E0\u8BED]", position: [6, 8] },
  { name: "\u563F\u54C8", code: "[\u563F\u54C8]", position: [6, 9] },
  { name: "\u6342\u8138", code: "[\u6342\u8138]", position: [7, 1] },
  { name: "\u5978\u7B11", code: "[\u5978\u7B11]", position: [7, 2] },
  { name: "\u673A\u667A", code: "[\u673A\u667A]", position: [7, 3] },
  { name: "\u76B1\u7709", code: "[\u76B1\u7709]", position: [7, 4] },
  { name: "\u8036", code: "[\u8036]", position: [7, 5] },
  { name: "\u5403\u74DC", code: "[\u5403\u74DC]", position: [7, 6] },
  { name: "\u52A0\u6CB9", code: "[\u52A0\u6CB9]", position: [7, 7] },
  { name: "\u6C57", code: "[\u6C57]", position: [7, 8] },
  { name: "\u5929\u554A", code: "[\u5929\u554A]", position: [7, 9] },
  { name: "Emm", code: "[Emm]", position: [8, 1] },
  { name: "\u793E\u4F1A\u793E\u4F1A", code: "[\u793E\u4F1A\u793E\u4F1A]", position: [8, 2] },
  { name: "\u65FA\u67F4", code: "[\u65FA\u67F4]", position: [8, 3] },
  { name: "\u597D\u7684", code: "[\u597D\u7684]", position: [8, 4] },
  { name: "\u6253\u8138", code: "[\u6253\u8138]", position: [8, 5] },
  { name: "\u54C7", code: "[\u54C7]", position: [8, 6] },
  { name: "\u7FFB\u767D\u773C", code: "[\u7FFB\u767D\u773C]", position: [8, 7] },
  { name: "666", code: "[666]", position: [8, 8] },
  { name: "\u8BA9\u6211\u770B\u770B", code: "[\u8BA9\u6211\u770B\u770B]", position: [8, 9] },
  { name: "\u53F9\u6C14", code: "[\u53F9\u6C14]", position: [9, 1] },
  { name: "\u82E6\u6DA9", code: "[\u82E6\u6DA9]", position: [9, 2] },
  { name: "\u88C2\u5F00", code: "[\u88C2\u5F00]", position: [9, 3] },
  { name: "\u5634\u5507", code: "[\u5634\u5507]", position: [9, 4] },
  { name: "\u7231\u5FC3", code: "[\u7231\u5FC3]", position: [9, 5] },
  { name: "\u5FC3\u788E", code: "[\u5FC3\u788E]", position: [9, 6] },
  { name: "\u62E5\u62B1", code: "[\u62E5\u62B1]", position: [9, 7] },
  { name: "\u5F3A", code: "[\u5F3A]", position: [9, 8] },
  { name: "\u5F31", code: "[\u5F31]", position: [9, 9] },
  { name: "\u63E1\u624B", code: "[\u63E1\u624B]", position: [10, 1] },
  { name: "\u80DC\u5229", code: "[\u80DC\u5229]", position: [10, 2] },
  { name: "\u62B1\u62F3", code: "[\u62B1\u62F3]", position: [10, 3] },
  { name: "\u52FE\u5F15", code: "[\u52FE\u5F15]", position: [10, 4] },
  { name: "\u62F3\u5934", code: "[\u62F3\u5934]", position: [10, 5] },
  { name: "OK", code: "[OK]", position: [10, 6] },
  { name: "\u5408\u5341", code: "[\u5408\u5341]", position: [10, 7] },
  { name: "\u5564\u9152", code: "[\u5564\u9152]", position: [10, 8] },
  { name: "\u5496\u5561", code: "[\u5496\u5561]", position: [10, 9] },
  { name: "\u86CB\u7CD5", code: "[\u86CB\u7CD5]", position: [11, 1] },
  { name: "\u73AB\u7470", code: "[\u73AB\u7470]", position: [11, 2] },
  { name: "\u51CB\u8C22", code: "[\u51CB\u8C22]", position: [11, 3] },
  { name: "\u83DC\u5200", code: "[\u83DC\u5200]", position: [11, 4] },
  { name: "\u70B8\u5F39", code: "[\u70B8\u5F39]", position: [11, 5] },
  { name: "\u4FBF\u4FBF", code: "[\u4FBF\u4FBF]", position: [11, 6] },
  { name: "\u6708\u4EAE", code: "[\u6708\u4EAE]", position: [11, 7] },
  { name: "\u592A\u9633", code: "[\u592A\u9633]", position: [11, 8] },
  { name: "\u5E86\u795D", code: "[\u5E86\u795D]", position: [11, 9] },
  { name: "\u793C\u7269", code: "[\u793C\u7269]", position: [12, 1] },
  { name: "\u7EA2\u5305", code: "[\u7EA2\u5305]", position: [12, 2] },
  { name: "\u798F", code: "[\u798F]", position: [12, 3] },
  { name: "\u70DF\u82B1", code: "[\u70DF\u82B1]", position: [12, 4] },
  { name: "\u7206\u7AF9", code: "[\u7206\u7AF9]", position: [12, 5] },
  { name: "\u732A\u5934", code: "[\u732A\u5934]", position: [12, 6] },
  { name: "\u8DF3\u8DF3", code: "[\u8DF3\u8DF3]", position: [12, 7] },
  { name: "\u53D1\u6296", code: "[\u53D1\u6296]", position: [12, 8] },
  { name: "\u8F6C\u5708", code: "[\u8F6C\u5708]", position: [12, 9] }
];
var emojiMap = /* @__PURE__ */ new Map();
wechatEmojis.forEach((emoji) => {
  emojiMap.set(emoji.code, emoji);
});
var emojiCodes = wechatEmojis.map((emoji) => emoji.code);
function calculateBackgroundPosition(position, emojiSize = 24, bgScale = 1.3) {
  const [row, col] = position;
  const rowIndex = row - 1;
  const colIndex = col - 1;
  const bgSize = size * bgScale;
  const offset = (bgSize - emojiSize) / 2;
  const x = -(colIndex * bgSize + offset);
  const y = -(rowIndex * bgSize + offset);
  return `${x}px ${y}px`;
}
function calculateBackgroundStyle(position, emojiSize = 24, bgScale = 1.3) {
  const bgSize = size * bgScale;
  const backgroundPosition = calculateBackgroundPosition(position, emojiSize, bgScale);
  const backgroundSize = `${bgSize * totalCols}px ${bgSize * totalRows}px`;
  return {
    backgroundPosition,
    backgroundSize,
    width: `${emojiSize}px`,
    height: `${emojiSize}px`,
    display: "inline-block",
    verticalAlign: "middle"
  };
}

// src/core/render.ts
function renderWechatEmoji(text, options = {}) {
  const {
    emojiSize = 24,
    bgScale = 1.3,
    spriteUrl = "./assets/sprite.png",
    className = ""
  } = options;
  return text.replace(/\[([^\]]+)\]/g, (match) => {
    const emoji = emojiMap.get(match);
    if (!emoji) {
      return match;
    }
    const style = calculateBackgroundStyle(emoji.position, emojiSize, bgScale);
    const styleString = Object.entries({
      ...style,
      backgroundImage: `url(${spriteUrl})`,
      backgroundRepeat: "no-repeat",
      position: "relative"
    }).map(([key, value]) => `${key.replace(/([A-Z])/g, "-$1").toLowerCase()}:${value}`).join(";");
    return `<span class="wechat-emoji ${className}" style="${styleString}" title="${emoji.name}"></span>`;
  });
}
function extractTextFromHtml(html) {
  return html.replace(/<span[^>]*title="([^"]*)"[^>]*><\/span>/g, (match, title) => {
    const emoji = Array.from(emojiMap.values()).find((e) => e.name === title);
    return emoji ? emoji.code : match;
  });
}

// src/utils/copy.ts
async function copyToClipboard(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.left = "-999999px";
    textArea.style.top = "-999999px";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    const result = document.execCommand("copy");
    document.body.removeChild(textArea);
    return result;
  } catch (error) {
    console.error("Failed to copy text: ", error);
    return false;
  }
}
function isClipboardSupported() {
  return !!(navigator.clipboard || document.execCommand);
}
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  copyToClipboard,
  emojiCodes,
  emojiMap,
  extractTextFromHtml,
  isClipboardSupported,
  renderWechatEmoji,
  wechatEmojis
});
