# Dodge Stutter Fix

???+ quote

    - Author: Managarm
    - Status: confirmed

Fixes the dodge stutter issue you get when duplicating dodges using ERClipGenerator.

Each roll variant has two CMSGs: regular and self-transition, which use the same animation, but separate ClipGenerators. However, when ERClipGenerator registers new clips, it reuses the same ClipGenerator for both CMSGs. The stuttering appears because the same ClipGenerator cannot run multiple times in parallel.

See [PossiblyShiba's tutorial](https://docs.google.com/document/d/1kWycrniv1i_TxDFkJIXzFWrgKLe8kFbZcpMd2PAVGPo/edit?tab=t.0) for additional details.
