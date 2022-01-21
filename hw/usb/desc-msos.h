#ifndef QEMU_HW_USB_DESC_MSOS_H
#define QEMU_HW_USB_DESC_MSOS_H

#define MSOS_DESC_INDEX (0xee)

/* generate microsoft string descriptor from structs */
int usb_desc_msos_str_desc(const char* str, uint8_t *dest, uint8_t ven_code);

#endif /* QEMU_HW_USB_DESC_MSOS_H */
