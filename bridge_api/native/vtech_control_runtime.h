#ifndef VTECH_CONTROL_RUNTIME_H
#define VTECH_CONTROL_RUNTIME_H

#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

/*
 * Header-only local control/state shim for an already-authenticated LF925
 * TUTK/Kalay session. It deliberately exposes only typed commands that were
 * observed and validated during protocol research. It is not a generic IOCtrl
 * proxy and does not contain pairing material or vendor SDK code.
 */

typedef int (*vtech_send_ioctl_fn)(void *opaque, uint32_t type,
                                   const uint8_t *payload, size_t len);

typedef struct vtech_runtime {
    char camera_id[33];
    char runtime_dir[PATH_MAX];
    char socket_path[PATH_MAX];
    char state_path[PATH_MAX];

    vtech_send_ioctl_fn send_ioctl;
    void *send_opaque;

    int fd;
    int running;
    pthread_t thread;
    pthread_mutex_t lock;

    int online;
    char session_state[24];
    int temperature_valid;
    double temperature_c;
    int humidity_valid;
    int humidity_percent;

    uint64_t updated_ms;
    uint64_t last_rx_ms;
    uint64_t last_video_ms;
    uint64_t last_audio_ms;
    uint64_t last_motion_ms;
    uint64_t last_sound_ms;
    uint64_t last_temperature_alert_ms;
} vtech_runtime;

static uint64_t vtech_runtime_now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (uint64_t)ts.tv_sec * 1000ULL + (uint64_t)ts.tv_nsec / 1000000ULL;
}

static void vtech_put_le32(uint8_t *dst, uint32_t value) {
    dst[0] = (uint8_t)(value & 0xff);
    dst[1] = (uint8_t)((value >> 8) & 0xff);
    dst[2] = (uint8_t)((value >> 16) & 0xff);
    dst[3] = (uint8_t)((value >> 24) & 0xff);
}

static int32_t vtech_get_le32s(const uint8_t *src) {
    uint32_t u = (uint32_t)src[0] |
                 ((uint32_t)src[1] << 8) |
                 ((uint32_t)src[2] << 16) |
                 ((uint32_t)src[3] << 24);
    return (int32_t)u;
}

static int vtech_runtime_write_state(vtech_runtime *rt) {
    char tmp[PATH_MAX];
    char json[1024];
    FILE *f;
    int n;

    pthread_mutex_lock(&rt->lock);
    rt->updated_ms = vtech_runtime_now_ms();
    n = snprintf(
        json, sizeof(json),
        "{\"schema_version\":1,\"camera_id\":\"%s\","
        "\"online\":%s,\"session_state\":\"%s\","
        "\"temperature_c\":%s,\"humidity_percent\":%s,"
        "\"updated_ms\":%llu,\"last_rx_ms\":%llu,"
        "\"last_video_ms\":%llu,\"last_audio_ms\":%llu,"
        "\"last_motion_ms\":%llu,\"last_sound_ms\":%llu,"
        "\"last_temperature_alert_ms\":%llu}\n",
        rt->camera_id,
        rt->online ? "true" : "false",
        rt->session_state,
        rt->temperature_valid ? "__TEMP__" : "null",
        rt->humidity_valid ? "__HUM__" : "null",
        (unsigned long long)rt->updated_ms,
        (unsigned long long)rt->last_rx_ms,
        (unsigned long long)rt->last_video_ms,
        (unsigned long long)rt->last_audio_ms,
        (unsigned long long)rt->last_motion_ms,
        (unsigned long long)rt->last_sound_ms,
        (unsigned long long)rt->last_temperature_alert_ms);

    if (n < 0 || (size_t)n >= sizeof(json)) {
        pthread_mutex_unlock(&rt->lock);
        return -1;
    }

    {
        char final_json[1024];
        char temp[64], hum[64];
        char *p = json;
        char *out = final_json;
        size_t left = sizeof(final_json);
        snprintf(temp, sizeof(temp), "%.1f", rt->temperature_c);
        snprintf(hum, sizeof(hum), "%d", rt->humidity_percent);
        while (*p && left > 1) {
            const char *rep = NULL;
            size_t token_len = 0;
            if (strncmp(p, "__TEMP__", 8) == 0) {
                rep = temp; token_len = 8;
            } else if (strncmp(p, "__HUM__", 7) == 0) {
                rep = hum; token_len = 7;
            }
            if (rep) {
                size_t rlen = strlen(rep);
                if (rlen >= left) break;
                memcpy(out, rep, rlen);
                out += rlen; left -= rlen; p += token_len;
            } else {
                *out++ = *p++; left--;
            }
        }
        *out = '\0';
        snprintf(json, sizeof(json), "%s", final_json);
    }
    pthread_mutex_unlock(&rt->lock);

    if (snprintf(tmp, sizeof(tmp), "%s.tmp.%ld", rt->state_path,
                 (long)getpid()) >= (int)sizeof(tmp)) return -1;
    f = fopen(tmp, "w");
    if (!f) return -1;
    (void)chmod(tmp, 0600);
    if (fputs(json, f) == EOF || fflush(f) != 0 || fsync(fileno(f)) != 0) {
        fclose(f); unlink(tmp); return -1;
    }
    if (fclose(f) != 0) { unlink(tmp); return -1; }
    if (rename(tmp, rt->state_path) != 0) { unlink(tmp); return -1; }
    return 0;
}

static int vtech_runtime_send(vtech_runtime *rt, uint32_t type,
                              const uint8_t *payload, size_t len) {
    if (!rt->send_ioctl) return -1;
    return rt->send_ioctl(rt->send_opaque, type, payload, len);
}

static int vtech_runtime_send_ptz(vtech_runtime *rt, const char *dir) {
    uint8_t p[8] = {0};
    if (strcmp(dir, "UP") == 0) p[0] = 0x01;
    else if (strcmp(dir, "DOWN") == 0) p[0] = 0x02;
    else if (strcmp(dir, "LEFT") == 0) p[0] = 0x03;
    else if (strcmp(dir, "RIGHT") == 0) p[0] = 0x06;
    else return -1;
    p[1] = 0x08;
    return vtech_runtime_send(rt, 0x1001, p, sizeof(p));
}

static int vtech_runtime_send_light_power(vtech_runtime *rt, int enabled,
                                          int brightness) {
    uint8_t p[4] = {0};
    if ((enabled != 0 && enabled != 1) ||
        (brightness != 12 && brightness != 57 && brightness != 98)) return -1;
    p[0] = (uint8_t)enabled;
    p[1] = (uint8_t)brightness;
    return vtech_runtime_send(rt, 0x07C8, p, sizeof(p));
}

static int vtech_runtime_send_light_preset(vtech_runtime *rt, int code) {
    uint8_t p[8] = {0};
    const int valid = (code >= 1 && code <= 7) || code == 0x10 ||
                      code == 0x11 || code == 0x12;
    if (!valid) return -1;
    p[0] = (uint8_t)code;
    return vtech_runtime_send(rt, 0x07D4, p, sizeof(p));
}

static int vtech_runtime_send_light_rgb(vtech_runtime *rt, int r, int g, int b) {
    uint8_t p[8] = {0x20, 0, 0, 0, 0, 0, 0, 0};
    if (r < 0 || r > 255 || g < 0 || g > 255 || b < 0 || b > 255) return -1;
    p[1] = (uint8_t)r; p[2] = (uint8_t)g; p[3] = (uint8_t)b;
    return vtech_runtime_send(rt, 0x07D4, p, sizeof(p));
}

static int vtech_runtime_send_light_timer(vtech_runtime *rt, int seconds) {
    uint8_t p[12] = {0};
    if (seconds != 0 && seconds != 900 && seconds != 1800 && seconds != 3600)
        return -1;
    if (seconds) vtech_put_le32(p, 1);
    vtech_put_le32(p + 4, (uint32_t)seconds);
    return vtech_runtime_send(rt, 0x07CC, p, sizeof(p));
}

static int vtech_runtime_send_lullaby_track(vtech_runtime *rt, int track) {
    uint8_t p[8] = {0};
    if (track < -1 || track > 10) return -1;
    vtech_put_le32(p + 4, (uint32_t)(int32_t)track);
    return vtech_runtime_send(rt, 0x0735, p, sizeof(p));
}

static int vtech_runtime_send_lullaby_params(vtech_runtime *rt, int volume,
                                              int timer_seconds) {
    uint8_t preflight[4] = {0};
    uint8_t p[24] = {0};
    if (volume != 1 && volume != 3 && volume != 5) return -1;
    if (timer_seconds != 0 && timer_seconds != 900 &&
        timer_seconds != 1800 && timer_seconds != 3600) return -1;
    if (vtech_runtime_send(rt, 0x07BA, preflight, sizeof(preflight)) != 0)
        return -1;
    vtech_put_le32(p + 4, (uint32_t)timer_seconds);
    vtech_put_le32(p + 8, (uint32_t)volume);
    vtech_put_le32(p + 12, 1);
    return vtech_runtime_send(rt, 0x0731, p, sizeof(p));
}

static int vtech_runtime_dispatch_one(vtech_runtime *rt, const char *cmd) {
    char dir[16];
    int a, b, c;
    if (strcmp(cmd, "PING") == 0) return 0;
    if (sscanf(cmd, "PTZ %15s", dir) == 1)
        return vtech_runtime_send_ptz(rt, dir);
    if (sscanf(cmd, "LIGHT POWER %d %d", &a, &b) == 2)
        return vtech_runtime_send_light_power(rt, a, b);
    if (sscanf(cmd, "LIGHT PRESET %d", &a) == 1)
        return vtech_runtime_send_light_preset(rt, a);
    if (sscanf(cmd, "LIGHT RGB %d %d %d", &a, &b, &c) == 3)
        return vtech_runtime_send_light_rgb(rt, a, b, c);
    if (sscanf(cmd, "LIGHT_TIMER %d", &a) == 1)
        return vtech_runtime_send_light_timer(rt, a);
    if (sscanf(cmd, "LULLABY_TRACK %d", &a) == 1)
        return vtech_runtime_send_lullaby_track(rt, a);
    if (sscanf(cmd, "LULLABY_PARAMS %d %d", &a, &b) == 2)
        return vtech_runtime_send_lullaby_params(rt, a, b);
    return -1;
}

static void vtech_trim(char *s) {
    char *end;
    while (*s == ' ' || *s == '\t') memmove(s, s + 1, strlen(s));
    end = s + strlen(s);
    while (end > s && (end[-1] == ' ' || end[-1] == '\t' ||
                       end[-1] == '\r' || end[-1] == '\n')) *--end = '\0';
}

static int vtech_runtime_dispatch_line(vtech_runtime *rt, const char *line) {
    char buf[512];
    char *save = NULL, *part;
    int count = 0;
    if (!line || strlen(line) >= sizeof(buf)) return -1;
    snprintf(buf, sizeof(buf), "%s", line);
    for (part = strtok_r(buf, ";", &save); part; part = strtok_r(NULL, ";", &save)) {
        vtech_trim(part);
        if (!*part) continue;
        if (++count > 2 || vtech_runtime_dispatch_one(rt, part) != 0) return -1;
    }
    return count ? 0 : -1;
}

static void vtech_runtime_touch(vtech_runtime *rt) {
    (void)vtech_runtime_write_state(rt);
}

static void vtech_runtime_note_video(vtech_runtime *rt) {
    pthread_mutex_lock(&rt->lock);
    rt->last_video_ms = vtech_runtime_now_ms();
    pthread_mutex_unlock(&rt->lock);
    vtech_runtime_touch(rt);
}

static void vtech_runtime_note_audio(vtech_runtime *rt) {
    pthread_mutex_lock(&rt->lock);
    rt->last_audio_ms = vtech_runtime_now_ms();
    pthread_mutex_unlock(&rt->lock);
    vtech_runtime_touch(rt);
}

static int vtech_runtime_handle_rx(vtech_runtime *rt, uint32_t type,
                                   const uint8_t *data, size_t len) {
    uint64_t now = vtech_runtime_now_ms();
    int changed = 0;
    if (!data) return 0;
    pthread_mutex_lock(&rt->lock);
    rt->last_rx_ms = now;

    if (type == 0x07D1 && len >= 12) {
        int32_t whole_c = vtech_get_le32s(data);
        rt->temperature_c = (double)whole_c + (double)data[9] / 10.0;
        rt->temperature_valid = 1;
        changed = 1;
    } else if (type == 0x07E2 && len >= 4 && data[0] == 1 && data[1] == 0) {
        rt->humidity_percent = (int)data[3];
        rt->humidity_valid = 1;
        changed = 1;
    } else if (type == 0x1FFF && len > 16) {
        if (data[16] == 0x01) {
            rt->last_motion_ms = now; changed = 1;
        } else if (data[16] == 0x15) {
            rt->last_sound_ms = now; changed = 1;
        } else if (data[16] == 0x16) {
            rt->last_temperature_alert_ms = now; changed = 1;
        }
    }
    pthread_mutex_unlock(&rt->lock);
    if (changed) vtech_runtime_touch(rt);
    return changed;
}

static void *vtech_runtime_control_thread(void *arg) {
    vtech_runtime *rt = (vtech_runtime *)arg;
    while (rt->running) {
        struct sockaddr_un peer;
        socklen_t peer_len = sizeof(peer);
        char buf[512];
        ssize_t n = recvfrom(rt->fd, buf, sizeof(buf) - 1, 0,
                             (struct sockaddr *)&peer, &peer_len);
        if (n < 0) {
            if (errno == EINTR) continue;
            if (!rt->running) break;
            continue;
        }
        buf[n] = '\0';
        const char *reply = vtech_runtime_dispatch_line(rt, buf) == 0 ? "OK" : "ERR invalid command";
        (void)sendto(rt->fd, reply, strlen(reply), 0,
                     (struct sockaddr *)&peer, peer_len);
    }
    return NULL;
}

static int vtech_runtime_init(vtech_runtime *rt, const char *camera_id,
                              const char *runtime_dir,
                              vtech_send_ioctl_fn send_ioctl, void *opaque) {
    if (!rt || !camera_id || !runtime_dir || !send_ioctl || strlen(camera_id) > 32)
        return -1;
    memset(rt, 0, sizeof(*rt));
    rt->fd = -1;
    rt->send_ioctl = send_ioctl;
    rt->send_opaque = opaque;
    snprintf(rt->camera_id, sizeof(rt->camera_id), "%s", camera_id);
    snprintf(rt->runtime_dir, sizeof(rt->runtime_dir), "%s", runtime_dir);
    if (snprintf(rt->socket_path, sizeof(rt->socket_path), "%s/%s.sock",
                 runtime_dir, camera_id) >= (int)sizeof(rt->socket_path)) return -1;
    if (snprintf(rt->state_path, sizeof(rt->state_path), "%s/%s.state.json",
                 runtime_dir, camera_id) >= (int)sizeof(rt->state_path)) return -1;
    snprintf(rt->session_state, sizeof(rt->session_state), "connected");
    rt->online = 1;
    return pthread_mutex_init(&rt->lock, NULL) == 0 ? 0 : -1;
}

static int vtech_runtime_start(vtech_runtime *rt) {
    struct sockaddr_un addr;
    if (mkdir(rt->runtime_dir, 0700) != 0 && errno != EEXIST) return -1;
    (void)chmod(rt->runtime_dir, 0700);
    unlink(rt->socket_path);
    rt->fd = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (rt->fd < 0) return -1;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    if (strlen(rt->socket_path) >= sizeof(addr.sun_path)) return -1;
    memcpy(addr.sun_path, rt->socket_path, strlen(rt->socket_path) + 1);
    if (bind(rt->fd, (struct sockaddr *)&addr, sizeof(addr)) != 0) return -1;
    (void)chmod(rt->socket_path, 0600);
    rt->running = 1;
    if (pthread_create(&rt->thread, NULL, vtech_runtime_control_thread, rt) != 0) {
        rt->running = 0; close(rt->fd); rt->fd = -1; return -1;
    }
    return vtech_runtime_write_state(rt);
}

static void vtech_runtime_set_session(vtech_runtime *rt, int online,
                                      const char *state) {
    pthread_mutex_lock(&rt->lock);
    rt->online = !!online;
    snprintf(rt->session_state, sizeof(rt->session_state), "%s",
             state ? state : (online ? "connected" : "offline"));
    pthread_mutex_unlock(&rt->lock);
    vtech_runtime_touch(rt);
}

static void vtech_runtime_stop(vtech_runtime *rt) {
    if (!rt) return;
    if (rt->running) {
        rt->running = 0;
        shutdown(rt->fd, SHUT_RDWR);
        close(rt->fd);
        rt->fd = -1;
        pthread_join(rt->thread, NULL);
    }
    unlink(rt->socket_path);
    vtech_runtime_set_session(rt, 0, "stopped");
    pthread_mutex_destroy(&rt->lock);
}

#endif /* VTECH_CONTROL_RUNTIME_H */
