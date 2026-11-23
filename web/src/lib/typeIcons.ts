import {
  AlignLeft, Binary, Calendar, CalendarClock, CheckSquare, CircleDot, Clock, Camera, FileUp, Gauge, Hash, IndianRupee, ListChecks,
  List, MapPin, Phone, PenLine, Sparkles, ToggleLeft, Type, UserRound, Video, type LucideIcon,
} from "lucide-react";

export const TYPE_ICON: Record<string, LucideIcon> = {
  short_text: Type, long_text: AlignLeft, number: Hash, currency: IndianRupee, phone: Phone, date: Calendar, time: Clock,
  datetime: CalendarClock, single_choice: CircleDot, multi_choice: ListChecks, yes_no: ToggleLeft, master_list: List,
  user_picker: UserRound, photo: Camera, video: Video, file: FileUp, signature: PenLine, gps: MapPin, derived: Sparkles, rating: Gauge,
};
export const iconFor = (type: string): LucideIcon => TYPE_ICON[type] ?? CheckSquare;
export { Binary };
