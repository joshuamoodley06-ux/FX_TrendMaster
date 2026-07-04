#!/bin/bash
awk '/function resolveCandleLoadWindow/,/^}/' electron/src/main.tsx
