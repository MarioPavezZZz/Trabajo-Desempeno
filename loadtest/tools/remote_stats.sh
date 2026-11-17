#!/usr/bin/env bash
# Recolector de recursos del SERVIDOR durante una prueba de carga remota.
#
#   bash remote_stats.sh <carpeta_salida> [intervalo_s]
#
# Lo lanza loadtest/run.ps1 -Ssh en la VM (vía scp + ssh) y se detiene cuando
# aparece <carpeta_salida>/.stop. Escribe dos CSV:
#
#   host.csv        CPU del host (user/system/iowait/steal/idle %), carga,
#                   memoria y swap, I/O de disco (KB/s y % de utilización)
#                   y red (KB/s) de la VM completa.
#   containers.csv  `docker stats` de cada contenedor (CPU %, memoria, red, disco).
#
# Por qué %steal: la VM es de la serie B de Azure (CPU por créditos). Cuando se
# agotan los créditos, el hipervisor limita la CPU y eso aparece como "steal".
# Sin esta columna, un estrangulamiento de la plataforma se confundiría con un
# cuello de botella de la aplicación.
#
# Solo usa /proc y docker (sin dependencias). Las columnas "epoch" permiten
# alinear con las métricas de k6 y de /metrics aunque los relojes usen otra zona.
set -u

OUT="${1:?carpeta de salida}"
INTERVAL="${2:-5}"
mkdir -p "$OUT"
HOST_CSV="$OUT/host.csv"
CONT_CSV="$OUT/containers.csv"
STOP="$OUT/.stop"
rm -f "$STOP"

# Interfaz de red principal y discos físicos (sin loop/sr ni particiones).
NET_IF="$(ip route show default 2>/dev/null | awk '{print $5; exit}')"
NET_IF="${NET_IF:-eth0}"
DISKS="$(ls /sys/block | grep -Ev '^(loop|sr|ram|zram)')"

echo "timestamp,epoch,segundo,cpu_user_pct,cpu_system_pct,cpu_iowait_pct,cpu_steal_pct,cpu_idle_pct,load1,mem_usada_mb,mem_disponible_mb,swap_usada_mb,disco_lectura_kbs,disco_escritura_kbs,disco_util_pct,red_rx_kbs,red_tx_kbs" > "$HOST_CSV"
echo "timestamp,epoch,segundo,contenedor,cpu_pct,memoria,red_io,disco_io" > "$CONT_CSV"

# Contadores acumulados: cpu (user nice system idle iowait irq softirq steal),
# disco (sectores leídos, escritos, ms de I/O) y red (bytes rx, tx).
cpu_counters() { awk '/^cpu /{print $2+$3, $4+$7+$8, $6, $9, $5}' /proc/stat; }
disk_counters() {
  awk -v disks="$DISKS" 'BEGIN{n=split(disks,a,"\n"); for(i=1;i<=n;i++) ok[a[i]]=1}
       ok[$3]{r+=$6; w+=$10; t=($13>t?$13:t)} END{print r+0, w+0, t+0}' /proc/diskstats
}
net_counters() { awk -v ifc="$NET_IF:" '$1==ifc{print $2, $10}' /proc/net/dev; }

START="$(date +%s.%N)"
read -r pu ps pio pst pid <<<"$(cpu_counters)"
read -r pdr pdw pdt <<<"$(disk_counters)"
read -r prx ptx <<<"$(net_counters)"
pt="$START"

while [ ! -f "$STOP" ]; do
  sleep "$INTERVAL"
  now="$(date +%s.%N)"
  read -r u s io st id <<<"$(cpu_counters)"
  read -r dr dw dt <<<"$(disk_counters)"
  read -r rx tx <<<"$(net_counters)"
  read -r load1 _ < /proc/loadavg
  mem="$(awk '/^MemTotal/{t=$2} /^MemAvailable/{a=$2} /^SwapTotal/{st=$2} /^SwapFree/{sf=$2}
              END{printf "%.0f,%.0f,%.0f", (t-a)/1024, a/1024, (st-sf)/1024}' /proc/meminfo)"
  stamp="$(TZ=America/Santiago date +%Y-%m-%dT%H:%M:%S)"

  awk -v now="$now" -v pt="$pt" -v start="$START" -v stamp="$stamp" -v load1="$load1" -v mem="$mem" \
      -v u="$u" -v s="$s" -v io="$io" -v st="$st" -v id="$id" \
      -v pu="$pu" -v ps="$ps" -v pio="$pio" -v pst="$pst" -v pid="$pid" \
      -v dr="$dr" -v dw="$dw" -v dt="$dt" -v pdr="$pdr" -v pdw="$pdw" -v pdt="$pdt" \
      -v rx="$rx" -v tx="$tx" -v prx="$prx" -v ptx="$ptx" 'BEGIN{
    el = now - pt
    du = u-pu; ds = s-ps; dio = io-pio; dst = st-pst; did = id-pid
    tot = du+ds+dio+dst+did; if (tot <= 0) tot = 1
    printf "%s,%.0f,%.1f,%.1f,%.1f,%.1f,%.1f,%.1f,%s,%s,%.1f,%.1f,%.1f,%.1f,%.1f\n", \
      stamp, now, now-start, 100*du/tot, 100*ds/tot, 100*dio/tot, 100*dst/tot, 100*did/tot, load1, mem, \
      (dr-pdr)*512/1024/el, (dw-pdw)*512/1024/el, 100*(dt-pdt)/(el*1000), \
      (rx-prx)/1024/el, (tx-ptx)/1024/el
  }' >> "$HOST_CSV"

  # docker stats tarda ~2 s: se toma después de la muestra del host.
  docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.NetIO}},{{.BlockIO}}' 2>/dev/null \
    | awk -v stamp="$stamp" -v now="$now" -v start="$START" '{printf "%s,%.0f,%.1f,%s\n", stamp, now, now-start, $0}' >> "$CONT_CSV"

  pu=$u; ps=$s; pio=$io; pst=$st; pid=$id
  pdr=$dr; pdw=$dw; pdt=$dt; prx=$rx; ptx=$tx; pt=$now
done
rm -f "$STOP"
