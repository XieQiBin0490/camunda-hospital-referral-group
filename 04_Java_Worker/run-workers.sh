#!/usr/bin/env bash
#
# Convenience wrapper for the hospital external workers.
#
#   ./run-workers.sh                      # build if needed, then run
#   REBUILD=1 ./run-workers.sh            # force a clean rebuild first
#   HPAS_PAYMENT_OUTCOME=DECLINED ./run-workers.sh
#
# Every configuration key in src/main/resources/workers.properties can be
# overridden from the environment as HPAS_<KEY> in upper case with dots replaced
# by underscores - see DEPLOYMENT.md.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

JAR="target/hospital-external-workers-1.0.0.jar"
MVN="mvn"
if [[ -x "$HERE/.tools/apache-maven-3.9.9/bin/mvn" ]]; then
  MVN="$HERE/.tools/apache-maven-3.9.9/bin/mvn"
fi

if [[ ! -f "$JAR" || "${REBUILD:-0}" == "1" ]]; then
  echo "==> building $JAR"
  "$MVN" -B -q clean package
fi

if [[ -z "${HPAS_GATEWAY_ADDRESS:-}" ]]; then
  echo "==> using the packaged gateway address (127.0.0.1:26500)"
  echo "    set HPAS_GATEWAY_ADDRESS to point somewhere else"
fi

# JAVA_OPTS is intentionally unquoted so it can carry several flags.
exec java ${JAVA_OPTS:-} -jar "$JAR" "$@"
