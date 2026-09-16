#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "vtech_control_runtime.h"

typedef struct capture {
    uint32_t type[8];
    uint8_t data[8][32];
    size_t len[8];
    int count;
} capture;

static int fake_send(void *opaque, uint32_t type, const uint8_t *payload, size_t len) {
    capture *c = (capture *)opaque;
    assert(c->count < 8);
    c->type[c->count] = type;
    c->len[c->count] = len;
    memcpy(c->data[c->count], payload, len);
    c->count++;
    return 0;
}

static void reset(capture *c) { memset(c, 0, sizeof(*c)); }

int main(void) {
    vtech_runtime rt;
    capture c;
    uint8_t t[12] = {22,0,0,0,0,0,0,0,0,5,0,0};
    uint8_t h[4] = {1,0,0,47};
    uint8_t e[17] = {0};

    reset(&c);
    assert(vtech_runtime_init(&rt, "cam1", "/tmp/lf925-test", fake_send, &c) == 0);

    assert(vtech_runtime_dispatch_line(&rt, "PTZ RIGHT") == 0);
    assert(c.count == 1 && c.type[0] == 0x1001 && c.len[0] == 8);
    assert(c.data[0][0] == 0x06 && c.data[0][1] == 0x08);

    reset(&c);
    assert(vtech_runtime_dispatch_line(&rt, "LIGHT POWER 0 98") == 0);
    assert(c.type[0] == 0x07C8 && c.data[0][0] == 0 && c.data[0][1] == 98);

    reset(&c);
    assert(vtech_runtime_dispatch_line(&rt, "LIGHT PRESET 5 ; LIGHT POWER 1 57") == 0);
    assert(c.count == 2 && c.type[0] == 0x07D4 && c.data[0][0] == 5);
    assert(c.type[1] == 0x07C8 && c.data[1][0] == 1 && c.data[1][1] == 57);

    reset(&c);
    assert(vtech_runtime_dispatch_line(&rt, "LIGHT RGB 12 34 56") == 0);
    assert(c.type[0] == 0x07D4 && c.data[0][0] == 0x20);
    assert(c.data[0][1] == 12 && c.data[0][2] == 34 && c.data[0][3] == 56);

    reset(&c);
    assert(vtech_runtime_dispatch_line(&rt, "LIGHT_TIMER 900") == 0);
    assert(c.type[0] == 0x07CC && c.len[0] == 12);
    assert(c.data[0][0] == 1 && c.data[0][4] == 0x84 && c.data[0][5] == 0x03);

    reset(&c);
    assert(vtech_runtime_dispatch_line(&rt, "LULLABY_TRACK -1") == 0);
    assert(c.type[0] == 0x0735 && c.data[0][4] == 0xff && c.data[0][7] == 0xff);

    reset(&c);
    assert(vtech_runtime_dispatch_line(&rt, "LULLABY_PARAMS 3 1800") == 0);
    assert(c.count == 2 && c.type[0] == 0x07BA && c.type[1] == 0x0731);

    assert(vtech_runtime_handle_rx(&rt, 0x07D1, t, sizeof(t)) == 1);
    assert(rt.temperature_valid && rt.temperature_c > 22.49 && rt.temperature_c < 22.51);
    assert(vtech_runtime_handle_rx(&rt, 0x07E2, h, sizeof(h)) == 1);
    assert(rt.humidity_valid && rt.humidity_percent == 47);

    e[16] = 0x01;
    assert(vtech_runtime_handle_rx(&rt, 0x1FFF, e, sizeof(e)) == 1);
    assert(rt.last_motion_ms != 0);
    e[16] = 0x15;
    assert(vtech_runtime_handle_rx(&rt, 0x1FFF, e, sizeof(e)) == 1);
    assert(rt.last_sound_ms != 0);
    e[16] = 0x16;
    assert(vtech_runtime_handle_rx(&rt, 0x1FFF, e, sizeof(e)) == 1);
    assert(rt.last_temperature_alert_ms != 0);

    assert(vtech_runtime_dispatch_line(&rt, "LIGHT POWER 1 99") != 0);
    assert(vtech_runtime_dispatch_line(&rt, "RAW 0x1234") != 0);

    pthread_mutex_destroy(&rt.lock);
    puts("native runtime tests: ok");
    return 0;
}
