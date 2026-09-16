# Official Android app observations

This document records completed interoperability research on the official Android client. It does not distribute or modify the APK.

## View All stream profile

The validated app path used IOCtrl `0x0719` when switching camera stream quality/profile.

Observed behavior:

- View All low-rate payload: byte offset 4 was `1`
- high-rate payload: all zeros
- overriding View All with the high-rate payload produced a large, repeatable increase in received media volume and visually smoother dual-camera playback on the tested setup

In one controlled 8-second comparison, the forced high-rate path received roughly `568883` bytes versus about `119369-137445` bytes in the original View All path. Treat these as measurements from one setup, not guaranteed bitrate specifications.

## Background/lifecycle guard

A narrow lifecycle guard was validated for a dedicated tablet deployment so the official app did not tear down the desired camera state during the tested background transition. The exact hook points are intentionally not shipped as a ready-made APK modification here because app versions and device lifecycle behavior can change.

## Frida research environment

The successful instrumentation path on the tested Huawei device used injected Frida Gadget/Zygisk-style loading rather than a conventional standalone `frida-server`. Broad native export enumeration destabilized the target. Narrow Java/static analysis and narrowly targeted hooks were substantially more reliable.

## Scope

These findings are useful for understanding the official client and reproducing observations on software/devices you are authorized to analyze. They are not required for the local Linux bridge or kiosk.
