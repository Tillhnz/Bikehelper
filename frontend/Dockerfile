# Das Frontend ist plattformunabhängig: immer nativ bauen (unter ARM-Emulation stürzt Node ab)
FROM --platform=$BUILDPLATFORM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
# Kameraanalyse: Bewegungserkennung (MediaPipe) samt Modell kommt beim Bauen ins Frontend und wird von dort ausgeliefert,
# der Browser lädt also nichts von Fremdservern. Bewusst nicht in package.json, damit package-lock.json unverändert bleibt.
RUN npm install --no-save --no-audit --no-fund @mediapipe/tasks-vision@0.10.14
COPY . .
RUN mkdir -p public/mediapipe && cp -r node_modules/@mediapipe/tasks-vision/wasm public/mediapipe/wasm \
 && wget -q -O public/mediapipe/pose_landmarker_lite.task \
    https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task \
 || (echo "Hinweis: Modell nicht ladbar, Kameraanalyse bleibt ohne Funktion" && mkdir -p public/mediapipe)
RUN npm run build

FROM nginx:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY page-headers.conf /etc/nginx/snippets/page-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
