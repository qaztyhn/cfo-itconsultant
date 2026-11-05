/**
 * i18next, mặc định tiếng Anh; định dạng ngày "Wed 4 Nov", giờ 24h theo múi giờ market (docs/03 mục 8).
 * Owner: Dev 3 (luồng C) — M0.
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";

void i18n.use(initReactI18next).init({ resources: { en: { translation: en } }, lng: "en", fallbackLng: "en" });

export default i18n;
