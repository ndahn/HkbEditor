# Rolling Arts Stutter Fix

???+ quote

    - Author: Kmstr
    - Status: verified

Same as for the dodge stutter, this fixes an issue which arises when the regular CMSG and self transition CMSG are using the same hkbClipGenerator instance.

Rolling arts have an additional self transition category that activates for some AOW like quickstep and bloodhound step after repeated use. Since there's a transition from self transition 1 to self transition 2 these clips must also be separate.
