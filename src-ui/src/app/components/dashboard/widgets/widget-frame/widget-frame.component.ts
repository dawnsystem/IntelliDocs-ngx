import { DragDropModule } from '@angular/cdk/drag-drop'
import { NgTemplateOutlet } from '@angular/common'
import { AfterViewInit, Component, Input, OnDestroy } from '@angular/core'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { LoadingComponentWithPermissions } from 'src/app/components/loading-component/loading.component'

@Component({
  selector: 'pngx-widget-frame',
  templateUrl: './widget-frame.component.html',
  styleUrls: ['./widget-frame.component.scss'],
  imports: [DragDropModule, NgxBootstrapIconsModule, NgTemplateOutlet],
})
export class WidgetFrameComponent
  extends LoadingComponentWithPermissions
  implements AfterViewInit, OnDestroy
{
  private showTimeoutId: any

  constructor() {
    super()
  }

  @Input()
  title: string

  @Input()
  loading: boolean = false

  @Input()
  draggable: any

  @Input()
  cardless: boolean = false

  @Input()
  badge: string

  ngAfterViewInit(): void {
    this.showTimeoutId = setTimeout(() => {
      this.show = true
      this.showTimeoutId = null
    }, 100)
  }

  override ngOnDestroy(): void {
    // Clean up timeout to prevent memory leak
    if (this.showTimeoutId) {
      clearTimeout(this.showTimeoutId)
      this.showTimeoutId = null
    }
    super.ngOnDestroy()
  }
}
